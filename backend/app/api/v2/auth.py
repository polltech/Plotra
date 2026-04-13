"""
Plotra Platform - Authentication API Endpoints
"""
from datetime import timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Form
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.auth import (
    authenticate_user, create_access_token, get_current_user,
    get_password_hash, require_admin
)
from app.models.user import User, UserRole, VerificationStatus
from app.api.schemas import (
    Token, LoginRequest, UserCreate, UserResponse, MessageResponse
)

router = APIRouter(tags=["Authentication"])


@router.post("/token", response_model=Token)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db)
):
    """
    OAuth2 token endpoint. Accepts phone number or email as username.
    """
    from sqlalchemy import select
    username = form_data.username

    print(f"LOGIN ATTEMPT: username={username}")

    try:
        user = await authenticate_user(db, username, form_data.password)
    except Exception as e:
        print(f"LOGIN ERROR: {type(e).__name__}: {e}")
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Login error")

    if not user:
        # Debug: check whether the identifier exists at all
        normalized = normalize_phone_with_country_code(username)
        result = await db.execute(
            select(User).where((User.phone == normalized) | (User.email == username))
        )
        found = result.scalars().first()
        if found:
            print(f"AUTH DEBUG: {username} found but password wrong")
        else:
            print(f"AUTH DEBUG: {username} not found (checked email and phone)")

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect phone number or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated"
        )

    access_token_expires = timedelta(minutes=settings.app.access_token_expire_minutes)
    role_value = user.role.value if hasattr(user.role, 'value') else str(user.role)
    access_token = create_access_token(
        data={"sub": str(user.id), "email": user.email, "role": role_value},
        expires_delta=access_token_expires
    )

    print(f"LOGIN SUCCESS: user_id={user.id}, role={role_value}")

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
    """
    from sqlalchemy import select
    import traceback
    
    try:
        # Check if email already exists
        result = await db.execute(
            select(User).where(User.email == user_data.email)
        )
        existing = result.scalars().first()

        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )

        # Check if phone already exists
        if user_data.phone_number:
            normalized_phone = normalize_phone_with_country_code(user_data.phone_number)
            if normalized_phone:
                phone_result = await db.execute(
                    select(User).where(User.phone == normalized_phone)
                )
                existing_phone = phone_result.scalars().first()
                if existing_phone:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Phone number already registered"
                    )
        
        # Check if national_id already exists
        if user_data.id_number:
            id_result = await db.execute(
                select(User).where(User.national_id == user_data.id_number)
            )
            if id_result.scalars().first():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="National ID already registered"
                )

        # Check if first_name + last_name combination already exists
        if user_data.first_name and user_data.last_name:
            name_result = await db.execute(
                select(User).where(
                    User.first_name.ilike(user_data.first_name),
                    User.last_name.ilike(user_data.last_name)
                )
            )
            if name_result.scalars().first():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="A user with this name already exists"
                )

        # Create user
        user = User(
            email=user_data.email,
            password_hash=get_password_hash(user_data.password),
            first_name=user_data.first_name,
            last_name=user_data.last_name,
            phone=user_data.phone_number,
            role=user_data.role,
            country=user_data.country or "Kenya",
            county=user_data.county,
            district=user_data.subcounty  # Map subcounty to district
        )
        
        # Store id_number in national_id if provided
        if user_data.id_number:
            user.national_id = user_data.id_number
        
        # Store additional optional fields in kyc_data JSON
        kyc_data = {}
        if user_data.gender:
            kyc_data['gender'] = user_data.gender
        if user_data.id_type:
            kyc_data['id_type'] = user_data.id_type
        if user_data.id_number:
            kyc_data['id_number'] = user_data.id_number
        if user_data.cooperative_code:
            kyc_data['cooperative_code'] = user_data.cooperative_code
        if user_data.payout_method:
            kyc_data['payout_method'] = user_data.payout_method
        if user_data.payout_recipient_id:
            kyc_data['payout_recipient_id'] = user_data.payout_recipient_id
        if user_data.payout_bank_name:
            kyc_data['payout_bank_name'] = user_data.payout_bank_name
        if user_data.payout_account_number:
            kyc_data['payout_account_number'] = user_data.payout_account_number
        
        if kyc_data:
            user.kyc_data = kyc_data
        
        db.add(user)
        await db.commit()
        await db.refresh(user)
        
        # Link user to cooperative if cooperative_code is provided
        if user_data.cooperative_code:
            from app.models.user import Cooperative, CooperativeMember
            # Find cooperative by code
            coop_query = select(Cooperative).where(Cooperative.code == user_data.cooperative_code)
            coop_result = await db.execute(coop_query)
            cooperative = coop_result.scalar_one_or_none()
            
            if cooperative:
                # Create cooperative membership
                membership = CooperativeMember(
                    user_id=user.id,
                    cooperative_id=cooperative.id,
                    is_active=True,
                    cooperative_role="member"
                )
                db.add(membership)
                await db.commit()
        
        return user
        
    except HTTPException:
        raise
    except IntegrityError as e:
        print(f"REGISTER ERROR: {str(e)}")
        await db.rollback()
        detail = "Registration failed due to a conflict."
        err_str = str(e).lower()
        if "national_id" in err_str:
            detail = "National ID already registered"
        elif "email" in err_str:
            detail = "Email already registered"
        elif "phone" in err_str:
            detail = "Phone number already registered"
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)
    except Exception as e:
        print(f"REGISTER ERROR: {str(e)}")
        print(traceback.format_exc())
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An internal error occurred. Please try again later. ({str(e)})"
        )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user)
):
    """
    Get current authenticated user's profile.
    """
    return current_user


@router.put("/profile", response_model=UserResponse)
async def update_user_profile(
    profile_data: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update current user's profile.
    """
    from sqlalchemy import select, update
    from app.models.user import User
    
    # Build update fields (only non-None values)
    update_fields = {}
    allowed_fields = [
        'phone', 'id_number', 'date_of_birth', 'gender',
        'county', 'subcounty', 'ward', 'address', 'first_name', 'last_name'
    ]
    
    for field in allowed_fields:
        if field in profile_data and profile_data[field] is not None:
            update_fields[field] = profile_data[field]
    
    # Handle kyc_data fields
    kyc_fields = ['id_type', 'gender', 'cooperative_code', 'payout_method', 
                  'payout_recipient_id', 'payout_bank_name', 'payout_account_number']
    
    # Build kyc_data if any kyc fields are provided
    kyc_updates = {}
    for field in kyc_fields:
        if field in profile_data and profile_data[field] is not None:
            kyc_updates[field] = profile_data[field]
    
    # Merge with existing kyc_data
    if kyc_updates:
        existing_kyc = current_user.kyc_data or {}
        existing_kyc.update(kyc_updates)
        update_fields['kyc_data'] = existing_kyc
    
    # Also store gender directly on user
    if 'gender' in profile_data and profile_data['gender'] is not None:
        update_fields['gender'] = profile_data['gender']
    
    if not update_fields:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No valid fields to update"
        )
    
    # Update user
    stmt = (
        update(User)
        .where(User.id == current_user.id)
        .values(**update_fields)
    )
    await db.execute(stmt)
    await db.commit()
    
    # Fetch updated user
    stmt = select(User).where(User.id == current_user.id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return user


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


@router.post("/refresh", response_model=Token)
async def refresh_token(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Refresh access token.
    Validates the current token and issues a new one.
    """
    from datetime import timedelta
    
    access_token_expires = timedelta(minutes=settings.app.access_token_expire_minutes)
    role_value = current_user.role.value if hasattr(current_user.role, 'value') else str(current_user.role)
    new_token = create_access_token(
        data={"sub": str(current_user.id), "email": current_user.email, "role": role_value},
        expires_delta=access_token_expires
    )
    
    return {
        "access_token": new_token,
        "token_type": "bearer",
        "expires_in": settings.app.access_token_expire_minutes * 60
    }


@router.get("/debug-phone")
async def debug_lookup_phone(
    phone: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Debug endpoint to check if phone number exists
    """
    from sqlalchemy import select
    
    # Normalize phone number
    digits = ''.join(c for c in phone if c.isdigit())
    if digits.startswith('254') and len(digits) == 12:
        normalized = '+' + digits
    elif len(digits) == 9 and digits.startswith(('7', '8', '9')):
        normalized = '+254' + digits
    elif phone.startswith('+') and len(digits) == 11:
        normalized = '+' + digits
    else:
        normalized = '+254' + digits[-9:] if len(digits) >= 9 else phone
    
    local_phone = normalized[-9:] if normalized and len(normalized) >= 9 else phone
    
    result = await db.execute(select(User).where(User.phone == normalized))
    user = result.scalar_one_or_none()
    
    if not user:
        result = await db.execute(select(User).where(User.phone.like(f'%{local_phone}%')))
        user = result.scalar_one_or_none()
    
    if not user:
        result = await db.execute(select(User).where(User.phone == phone))
        user = result.scalar_one_or_none()
    
    return {
        "input_phone": phone,
        "normalized": normalized,
        "local_phone": local_phone,
        "found": user is not None,
        "user_id": user.id if user else None,
        "user_phone": user.phone if user else None,
        "user_email": user.email if user else None
    }


@router.get("/check/email")
async def check_email_exists(
    email: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Check if email already exists
    """
    from sqlalchemy import select
    
    result = await db.execute(select(User).where(User.email == email.lower()))
    exists = result.scalars().first() is not None
    
    return {"exists": exists, "email": email}


@router.get("/check/phone")
async def check_phone_exists(
    phone: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Check if phone number already exists
    """
    from app.core.auth import normalize_phone_with_country_code
    
    normalized_phone = normalize_phone_with_country_code(phone)
    
    result = await db.execute(select(User).where(User.phone == normalized_phone))
    exists = result.scalars().first() is not None
    
    return {"exists": exists, "phone": phone}


@router.get("/check/id-number")
async def check_id_number_exists(
    id_number: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Check if national ID number already exists
    """
    from sqlalchemy import select
    
    result = await db.execute(select(User).where(User.national_id == id_number))
    exists = result.scalars().first() is not None
    
    return {"exists": exists, "id_number": id_number}


@router.get("/check/name")
async def check_name_exists(
    first_name: str,
    last_name: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Check if first_name + last_name combination already exists
    """
    from sqlalchemy import select
    
    result = await db.execute(
        select(User).where(
            User.first_name.ilike(first_name),
            User.last_name.ilike(last_name)
        )
    )
    exists = result.scalars().first() is not None
    
    return {"exists": exists, "first_name": first_name, "last_name": last_name}


@router.get("/check/coop-registration-number")
async def check_coop_registration_number(
    registration_number: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Check if cooperative registration number already exists
    """
    from sqlalchemy import select
    from app.models.user import Cooperative
    
    result = await db.execute(select(Cooperative).where(Cooperative.registration_number == registration_number))
    exists = result.scalars().first() is not None
    
    return {"exists": exists, "registration_number": registration_number}


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
    from app.core.email import send_email
    
    # Find user by email
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User with this email not found"
        )
    
    # Generate reset token
    reset_token = str(uuid.uuid4())
    reset_expires = datetime.utcnow() + timedelta(hours=24)  # Token valid for 24 hours
    
    # Update user with reset token and expiry
    user.password_reset_token = reset_token
    user.password_reset_expires = reset_expires
    await db.commit()
    
    # Send reset email
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
    
    return {"message": "Password reset link sent to your email"}


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
    from app.core.auth import get_password_hash
    
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
    from app.models.user import UserStatus
    if user.status == UserStatus.PENDING_VERIFICATION:
        user.status = UserStatus.ACTIVE
    
    await db.commit()
    
    return {"message": "Password reset successfully. Your account is now active."}


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
        "role": current_user.role.value
    }


# =============================================================================
# Phone OTP Verification Endpoints
# =============================================================================
import random
import string
from datetime import datetime, timedelta
from sqlalchemy import select

# In-memory storage for OTPs (in production, use Redis or database)
otp_store: dict = {}


def generate_otp() -> str:
    """Generate a 6-digit OTP."""
    return ''.join(random.choices(string.digits, k=6))


def normalize_phone_with_country_code(phone: str, country_code: str = "+254") -> Optional[str]:
    """
    Normalize phone number to include country code.
    Handles various formats: 0712345678, 712345678, +254712345678, 254712345678
    """
    if not phone:
        return None
    
    # Remove all non-digit characters
    digits = ''.join(c for c in phone if c.isdigit())
    
    # If it's exactly 12 digits and starts with country code (254)
    if digits.startswith('254') and len(digits) == 12:
        return '+' + digits
    # If it starts with + and has 11 digits (254 + 9)
    elif phone.startswith('+') and len(digits) == 11:
        return '+' + digits
    # If it's 9 digits (local number starting with 7, 8, or 9)
    elif len(digits) == 9 and digits.startswith(('7', '8', '9')):
        return country_code + digits
    # If it starts with 0, remove the leading 0 and add country code
    elif digits.startswith('0') and len(digits) == 10:
        return country_code + digits[1:]
    # If it already has + prefix but something went wrong
    elif phone.startswith('+'):
        return country_code + digits if len(digits) >= 9 else None
    
    # Default: try to extract valid digits and return with country code
    if len(digits) >= 9:
        return country_code + digits[-9:]  # Take last 9 digits
    
    return None


@router.post("/otp/send")
async def send_otp(
    phone_number: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    """
    Send OTP to the provided phone number.
    Requires phone number with country code (e.g., +254712345678)
    """
    # Normalize phone number with country code
    normalized_phone = normalize_phone_with_country_code(phone_number)
    
    if not normalized_phone:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid phone number format"
        )
    
    # Validate phone format (basic validation)
    if not normalized_phone.startswith('+') or len(normalized_phone) < 12:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Phone number must include country code (e.g., +254...)"
        )
    
    # Generate OTP
    otp = generate_otp()
    
    # Store OTP with expiration (5 minutes)
    otp_store[normalized_phone] = {
        'otp': otp,
        'expires': datetime.utcnow() + timedelta(minutes=5),
        'attempts': 0
    }
    
    # Send OTP via SMS
    from app.core.sms import send_otp_sms
    sms_sent = await send_otp_sms(normalized_phone, otp)
    
    if not sms_sent:
        # Log anyway for debugging if SMS fails
        print(f"OTP for {normalized_phone}: {otp}")
    
    return {
        "message": "OTP sent successfully",
        "phone": normalized_phone[-4:].rjust(len(normalized_phone), '*'),  # Mask phone number
        "expires_in": 300  # 5 minutes in seconds
    }


@router.post("/otp/verify")
async def verify_otp(
    phone_number: str = Form(...),
    otp: str = Form(..., min_length=6, max_length=6),
    db: AsyncSession = Depends(get_db)
):
    """
    Verify the OTP sent to the phone number.
    Returns a verification token on success.
    """
    # Normalize phone number
    normalized_phone = normalize_phone_with_country_code(phone_number)
    
    if not normalized_phone:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid phone number format"
        )
    
    # Find stored OTP
    stored_data = otp_store.get(normalized_phone)
    
    if not stored_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No OTP found. Please request a new OTP."
        )
    
    # Check if OTP has expired
    if stored_data['expires'] < datetime.utcnow():
        del otp_store[normalized_phone]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OTP has expired. Please request a new OTP."
        )
    
    # Check attempts
    if stored_data['attempts'] >= 3:
        del otp_store[normalized_phone]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Too many failed attempts. Please request a new OTP."
        )
    
    # Verify OTP
    if stored_data['otp'] != otp:
        stored_data['attempts'] += 1
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OTP. Please try again."
        )
    
    # OTP verified successfully - generate a verification token
    from app.core.auth import create_access_token
    
    verification_token = create_access_token(
        data={
            "sub": "phone_verification",
            "phone": normalized_phone,
            "verified": True
        },
        expires_delta=timedelta(hours=1)
    )
    
    # Remove OTP from store after successful verification
    del otp_store[normalized_phone]
    
    return {
        "message": "Phone number verified successfully",
        "verification_token": verification_token,
        "phone": normalized_phone
    }


@router.post("/otp/resend")
async def resend_otp(
    phone_number: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    """
    Resend OTP to the provided phone number.
    Removes any existing OTP and generates a new one.
    """
    normalized_phone = normalize_phone_with_country_code(phone_number)
    
    if not normalized_phone:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid phone number format"
        )
    
    # Remove any existing OTP
    if normalized_phone in otp_store:
        del otp_store[normalized_phone]
    
    # Generate new OTP
    otp = generate_otp()
    
    # Store OTP with expiration (5 minutes)
    otp_store[normalized_phone] = {
        'otp': otp,
        'expires': datetime.utcnow() + timedelta(minutes=5),
        'attempts': 0
    }
    
    # Send OTP via SMS
    from app.core.sms import send_otp_sms
    sms_sent = await send_otp_sms(normalized_phone, otp)
    
    if not sms_sent:
        print(f"OTP for {normalized_phone}: {otp}")
    
    return {
        "message": "OTP sent successfully",
        "phone": normalized_phone[-4:].rjust(len(normalized_phone), '*'),
        "expires_in": 300
    }
