"""
Plotra Platform - Authentication API Endpoints
"""
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Form
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.auth import (
    authenticate_user, create_access_token, get_current_user,
    get_password_hash, require_admin
)
from app.models.user import User, UserRole, VerificationStatus
from app.api.schemas import (
    Token, LoginRequest, UserCreate, UserResponse, UserUpdate, MessageResponse
)

router = APIRouter(tags=["Authentication"])


@router.post("/token", response_model=Token)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db)
):
    """
    OAuth2 compatible token login.
    Supports both JSON and form-encoded requests.
    """
    user = await authenticate_user(db, form_data.username, form_data.password)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated"
        )
    
    access_token_expires = timedelta(minutes=settings.app.access_token_expire_minutes)
    # Convert role to string if it's an enum
    role_value = user.role.value if hasattr(user.role, 'value') else str(user.role)
    access_token = create_access_token(
        data={"sub": str(user.id), "email": user.email, "role": role_value},
        expires_delta=access_token_expires
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": settings.app.access_token_expire_minutes * 60
    }


@router.post("/token-form", response_model=Token)
async def login_form(
    username: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    """
    Form-encoded login endpoint for browser compatibility.
    """
    user = await authenticate_user(db, username, password)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated"
        )
    
    access_token_expires = timedelta(minutes=settings.app.access_token_expire_minutes)
    # Convert role to string if it's an enum
    role_value = user.role.value if hasattr(user.role, 'value') else str(user.role)
    access_token = create_access_token(
        data={"sub": str(user.id), "email": user.email, "role": role_value},
        expires_delta=access_token_expires
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": settings.app.access_token_expire_minutes * 60
    }


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register_user(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    Register a new user.
    New users are created with PENDING verification status.
    Farmers can optionally specify their cooperative.
    """
    from sqlalchemy import select
    from app.models.user import Cooperative
    
    # Check if email already exists
    result = await db.execute(
        select(User).where(User.email == user_data.email)
    )
    existing = result.scalar_one_or_none()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Validate cooperative code if provided
    cooperative = None
    cooperative_id = None
    if user_data.cooperative_code:
        result = await db.execute(
            select(Cooperative).where(Cooperative.code == user_data.cooperative_code.upper())
        )
        cooperative = result.scalar_one_or_none()
        if not cooperative:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid cooperative code"
            )
        cooperative_id = cooperative.id
    
    # Create user
    print(f"DEBUG: Creating user with role: {user_data.role}")
    user = User(
        email=user_data.email,
        password_hash=get_password_hash(user_data.password),
        first_name=user_data.first_name,
        last_name=user_data.last_name,
        phone_number=user_data.phone_number,
        role=user_data.role,
        country=user_data.country,
        county=user_data.county,
        subcounty=user_data.subcounty,
        # New fields
        gender=user_data.gender,
        id_type=user_data.id_type,
        id_number=user_data.id_number,
        payout_method=user_data.payout_method,
        payout_recipient_id=user_data.payout_recipient_id,
        payout_bank_name=user_data.payout_bank_name,
        payout_account_number=user_data.payout_account_number,
        # Cooperative membership
        cooperative_id=cooperative_id,
        belongs_to_cooperative=bool(cooperative_id),
        verification_status=VerificationStatus.PENDING
    )
    
    db.add(user)
    await db.commit()
    await db.refresh(user)
    
    return user


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user)
):
    """
    Get current authenticated user's profile.
    """
    return current_user


@router.post("/change-password", response_model=MessageResponse)
async def change_password(
    current_password: str = Form(...),
    new_password: str = Form(..., min_length=8),
    confirm_password: str = Form(..., min_length=8),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Change user password.
    """
    from app.core.auth import verify_password
    
    # Verify current password
    if not verify_password(current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect"
        )
    
    # Confirm new password matches
    if new_password != confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New passwords do not match"
        )
    
    # Update password
    current_user.password_hash = get_password_hash(new_password)
    await db.commit()
    
    return {"message": "Password changed successfully"}


@router.post("/logout", response_model=MessageResponse)
async def logout():
    """
    Logout endpoint.
    Note: JWT tokens are stateless, so this is mainly for client-side cleanup.
    """
    return {"message": "Successfully logged out"}


@router.get("/verify-token")
async def verify_token(
    current_user: User = Depends(get_current_user)
):
    """
    Verify if the current token is valid.
    """
    return {
        "valid": True,
        "user_id": current_user.id,
        "email": current_user.email,
        "role": current_user.role.value if hasattr(current_user.role, 'value') else current_user.role
    }


@router.post("/refresh", response_model=Token)
async def refresh_token(
    current_user: User = Depends(get_current_user)
):
    """
    Refresh the current JWT token. Returns a new token for the authenticated user.
    """
    access_token_expires = timedelta(minutes=settings.app.access_token_expire_minutes)
    role_value = current_user.role.value if hasattr(current_user.role, 'value') else str(current_user.role)
    access_token = create_access_token(
        data={"sub": str(current_user.id), "email": current_user.email, "role": role_value},
        expires_delta=access_token_expires
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": settings.app.access_token_expire_minutes * 60
    }


@router.put("/profile", response_model=UserResponse)
async def update_profile(
    profile_data: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update current user's profile. Works for all roles.
    """
    update_data = profile_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if hasattr(current_user, field):
            setattr(current_user, field, value)
    await db.commit()
    await db.refresh(current_user)
    return current_user


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(
    email: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    """
    Request a password reset token.
    """
    from sqlalchemy import select
    from datetime import datetime, timedelta
    import uuid
    
    try:
        from app.core.email import send_email
    except ImportError:
        # Email service not configured, still allow the flow but log warning
        print("WARNING: Email service not configured")
        send_email = None
    
    # Find user by email
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    
    if not user:
        # Don't reveal if user exists
        return {"message": "Password reset link sent to your email if the account exists"}
    
    # Generate reset token
    reset_token = str(uuid.uuid4())
    reset_expires = datetime.utcnow() + timedelta(hours=24)  # Token valid for 24 hours
    
    # Update user with reset token and expiry
    user.password_reset_token = reset_token
    user.password_reset_expires = reset_expires
    await db.commit()
    
    # Send reset email if email service is available
    if send_email:
        reset_link = f"http://localhost:8080/reset-password?token={reset_token}"
        subject = "Plotra Platform - Password Reset Request"
        text_content = f"""
        We received a request to reset your password for the Plotra Platform.
        
        To reset your password, please click the link below:
        
        {reset_link}
        
        This link will expire in 24 hours for security reasons.
        
        If you did not request a password reset, please ignore this email or contact our support team at support@plotra.africa.
        """
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Password Reset Request</title>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    background-color: #f5f5f5;
                    margin: 0;
                    padding: 0;
                }}
                .container {{
                    max-width: 600px;
                    margin: 20px auto;
                    padding: 20px;
                    background-color: #ffffff;
                    border-radius: 8px;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                }}
                .header {{
                    text-align: center;
                    padding: 20px 0;
                    border-bottom: 1px solid #eeeeee;
                }}
                .content {{
                    padding: 20px 0;
                    line-height: 1.6;
                }}
                .button {{
                    display: inline-block;
                    background-color: #6f4e37;
                    color: white;
                    padding: 12px 24px;
                    text-decoration: none;
                    border-radius: 4px;
                    margin: 20px 0;
                    font-weight: bold;
                }}
                .footer {{
                    text-align: center;
                    padding: 20px 0;
                    border-top: 1px solid #eeeeee;
                    color: #666666;
                    font-size: 14px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1 style="color: #6f4e37;">Plotra Platform</h1>
                    <p>Password Reset Request</p>
                </div>
                
                <div class="content">
                    <p>We received a request to reset your password for the Plotra Platform.</p>
                    
                    <p>To reset your password, please click the button below:</p>
                    
                    <p style="text-align: center;">
                        <a href="{reset_link}" class="button">Reset Password</a>
                    </p>
                    
                    <p>This link will expire in 24 hours for security reasons.</p>
                    
                    <p>If you did not request a password reset, please ignore this email or contact our support team at <a href="mailto:support@plotra.africa">support@plotra.africa</a>.</p>
                </div>
                
                <div class="footer">
                    <p>&copy; 2026 Plotra Platform. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        await send_email(email, subject, html_content, text_content)
    
    return {"message": "Password reset link sent to your email if the account exists"}


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(
    token: str = Form(...),
    new_password: str = Form(..., min_length=8),
    confirm_password: str = Form(..., min_length=8),
    db: AsyncSession = Depends(get_db)
):
    """
    Reset password using a valid reset token.
    """
    from sqlalchemy import select
    from datetime import datetime
    
    # Verify passwords match
    if new_password != confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Passwords do not match"
        )
    
    # Find user with valid reset token
    result = await db.execute(
        select(User).where(User.password_reset_token == token)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired password reset token"
        )
    
    # Check if token has expired
    if user.password_reset_expires and user.password_reset_expires < datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password reset token has expired"
        )
    
    # Update password and clear reset token
    user.password_hash = get_password_hash(new_password)
    user.password_reset_token = None
    user.password_reset_expires = None
    
    # Activate the user if they were pending verification
    try:
        from app.models.user import UserStatus
        if hasattr(user, 'status') and user.status == UserStatus.PENDING_VERIFICATION:
            user.status = UserStatus.ACTIVE
    except Exception:
        pass  # Status field may not exist
    
    await db.commit()
    
    return {"message": "Password reset successfully. Your account is now active."}


# ---------------------------------------------------------------------------
# OTP (Phone Verification)
# ---------------------------------------------------------------------------

import random
import string
from datetime import datetime

# In-memory OTP store (use Redis in production)
_otp_store: dict = {}


def _generate_otp() -> str:
    """Generate a 6-digit OTP."""
    return ''.join(random.choices(string.digits, k=6))


def _normalize_phone(phone: str, country_code: str = "+254") -> str:
    """Normalize phone number to E.164 format with country code."""
    if not phone:
        return None
    digits = ''.join(c for c in phone if c.isdigit())
    if digits.startswith('254') and len(digits) == 12:
        return '+' + digits
    elif len(digits) == 9 and digits[0] in ('7', '8', '9'):
        return country_code + digits
    elif digits.startswith('0'):
        return country_code + digits[1:]
    elif phone.startswith('+'):
        return '+' + digits
    return country_code + digits if len(digits) == 9 else phone


@router.post("/otp/send")
async def send_otp(
    phone_number: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    """Send a 6-digit OTP to the provided phone number."""
    normalized = _normalize_phone(phone_number)
    if not normalized or not normalized.startswith('+') or len(normalized) < 12:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid phone number format. Include country code (e.g., +254...)"
        )

    otp = _generate_otp()
    _otp_store[normalized] = {
        'otp': otp,
        'expires': datetime.utcnow() + timedelta(minutes=5),
        'attempts': 0,
    }

    from app.core.sms import send_otp_sms
    sms_sent = await send_otp_sms(normalized, otp)
    if not sms_sent:
        print(f"OTP for {normalized}: {otp}")

    masked = normalized[-4:].rjust(len(normalized), '*')
    return {"message": "OTP sent successfully", "phone": masked, "expires_in": 300}


@router.post("/otp/verify")
async def verify_otp(
    phone_number: str = Form(...),
    otp: str = Form(..., min_length=6, max_length=6),
    db: AsyncSession = Depends(get_db)
):
    """Verify the OTP sent to a phone number and return a verification token."""
    normalized = _normalize_phone(phone_number)
    if not normalized:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid phone number format")

    stored = _otp_store.get(normalized)
    if not stored:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No OTP found. Please request a new one.")

    if stored['expires'] < datetime.utcnow():
        del _otp_store[normalized]
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP has expired. Please request a new one.")

    if stored['attempts'] >= 3:
        del _otp_store[normalized]
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Too many failed attempts. Please request a new OTP.")

    if stored['otp'] != otp:
        stored['attempts'] += 1
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OTP. Please try again.")

    verification_token = create_access_token(
        data={"sub": "phone_verification", "phone": normalized, "verified": True},
        expires_delta=timedelta(hours=1)
    )
    del _otp_store[normalized]

    return {"message": "Phone number verified successfully", "verification_token": verification_token, "phone": normalized}


@router.post("/otp/resend")
async def resend_otp(
    phone_number: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    """Resend OTP — clears any existing OTP and generates a fresh one."""
    normalized = _normalize_phone(phone_number)
    if not normalized or not normalized.startswith('+') or len(normalized) < 12:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid phone number format. Include country code (e.g., +254...)"
        )

    _otp_store.pop(normalized, None)

    otp = _generate_otp()
    _otp_store[normalized] = {
        'otp': otp,
        'expires': datetime.utcnow() + timedelta(minutes=5),
        'attempts': 0,
    }

    from app.core.sms import send_otp_sms
    sms_sent = await send_otp_sms(normalized, otp)
    if not sms_sent:
        print(f"OTP for {normalized}: {otp}")

    masked = normalized[-4:].rjust(len(normalized), '*')
    return {"message": "OTP sent successfully", "phone": masked, "expires_in": 300}
