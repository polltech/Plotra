"""
Plotra Platform - Authentication Module
JWT-based authentication with role-based access control
"""
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from jose import JWTError, jwt
import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from .config import settings
from .database import get_db
from app.models.user import User, UserRole
from app.models.verification import VerificationStatus


# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v2/auth/token",
    scheme_name="JWT",
)

# Form-based OAuth2 for browser compatibility
oauth2_scheme_form = OAuth2PasswordBearer(
    tokenUrl="/api/v2/auth/token-form",
    scheme_name="JWT Form",
    auto_error=False,
)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    try:
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except Exception as e:
        print(f"Password verification error: {e}")
        return False


def get_password_hash(password: str) -> str:
    """Hash a password"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create a JWT access token.
    
    Args:
        data: Payload data to encode
        expires_delta: Token expiration time
        
    Returns:
        Encoded JWT token string
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(
            minutes=settings.app.access_token_expire_minutes
        )
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(
        to_encode,
        settings.app.secret_key,
        algorithm=settings.app.algorithm
    )
    
    return encoded_jwt


def decode_token(token: str) -> Dict[str, Any]:
    """
    Decode and validate a JWT token.
    
    Args:
        token: JWT token string
        
    Returns:
        Decoded token payload
        
    Raises:
        HTTPException: If token is invalid or expired
    """
    try:
        payload = jwt.decode(
            token,
            settings.app.secret_key,
            algorithms=[settings.app.algorithm]
        )
        return payload
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Could not validate credentials: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    Get the current authenticated user from JWT token.
    
    Args:
        token: JWT token from Authorization header
        db: Database session
        
    Returns:
        User object
        
    Raises:
        HTTPException: If user not found or inactive
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    payload = decode_token(token)
    user_id = payload.get("sub")
    
    if user_id is None:
        raise credentials_exception
    
    # Fetch user from database
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    
    if user is None:
        raise credentials_exception
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated"
        )
    
    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Ensure the current user is active.
    
    Args:
        current_user: Current authenticated user
        
    Returns:
        Active User object
        
    Raises:
        HTTPException: If user is not active
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated"
        )
    return current_user


def require_role(allowed_roles: list[UserRole]):
    """
    Dependency factory for role-based access control.
    
    Args:
        allowed_roles: List of roles allowed to access the endpoint
        
    Returns:
        Dependency function
        
    Raises:
        HTTPException: If user role not in allowed list
    """
    async def role_checker(current_user: User = Depends(get_current_active_user)) -> User:
        user_role = current_user.role.value if hasattr(current_user.role, 'value') else str(current_user.role)
        # Plotra admin has full access
        if user_role.lower() == UserRole.KIPAWA_ADMIN.value.lower():
            return current_user
            
        if user_role.lower() not in [r.value.lower() for r in allowed_roles]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required roles: {', '.join(r.value for r in allowed_roles)}"
            )
        return current_user
    
    return role_checker


# Pre-configured role checkers
require_farmer = require_role([UserRole.FARMER])
require_coop_admin = require_role([UserRole.COOPERATIVE_OFFICER])
require_plotra_admin = require_role([UserRole.KIPAWA_ADMIN])
require_platform_admin = require_role([UserRole.KIPAWA_ADMIN])
require_auditor = require_role([UserRole.EUDR_REVIEWER])
require_admin = require_role([UserRole.KIPAWA_ADMIN, UserRole.COOPERATIVE_OFFICER, UserRole.EUDR_REVIEWER])


async def authenticate_user(
    db: AsyncSession,
    email: str,
    password: str
) -> Optional[User]:
    """
    Authenticate a user by email, phone number, or username and password.
    
    Args:
        db: Database session
        email: User email, phone number, or username
        password: Plain text password
        
    Returns:
        User object if authenticated, None otherwise
    """
    print(f"[AUTH] Attempting login with: {email}")
    
    # Check if it's a phone number (starts with + or digits only)
    is_phone = email.startswith('+') or email.isdigit()
    
    if is_phone:
        # Normalize phone number
        from app.api.v2.auth import normalize_phone_with_country_code
        normalized_phone = normalize_phone_with_country_code(email)
        
        # Try to find user by phone number
        if normalized_phone:
            result = await db.execute(
                select(User).where(User.phone == normalized_phone)
            )
            user = result.scalars().first()
            if not user:
                # Try without country code (just the 9 digits)
                local_number = normalized_phone[-9:] if len(normalized_phone) >= 9 else normalized_phone
                result = await db.execute(
                    select(User).where(User.phone.like(f'%{local_number}'))
                )
                user = result.scalars().first()
            if user:
                # Verify password
                if not verify_password(password, user.password_hash):
                    user.failed_login_attempts += 1
                    if user.failed_login_attempts >= 5:
                        user.is_locked = True
                    await db.commit()
                    return None
                if user.is_locked:
                    return None
                user.failed_login_attempts = 0
                user.last_login = datetime.utcnow()
                await db.commit()
                return user
    else:
        # Try to find user by email
        result = await db.execute(
            select(User).where(User.email == email)
        )
        user = result.scalars().first()
    
    if not user:
        return None
    
    if not verify_password(password, user.password_hash):
        # Increment failed login attempts
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= 5:
            user.is_locked = True
        await db.commit()
        return None
    
    # Check if account is locked
    if user.is_locked:
        return None
    
    # Reset failed attempts on successful login
    user.failed_login_attempts = 0
    user.last_login = datetime.utcnow()
    await db.commit()
    
    return user


async def create_user(
    db: AsyncSession,
    email: str,
    password: str,
    first_name: str,
    last_name: str,
    role: UserRole = UserRole.FARMER,
    phone_number: Optional[str] = None,
    **kwargs
) -> User:
    """
    Create a new user with hashed password.
    
    Args:
        db: Database session
        email: User email
        password: Plain text password
        first_name: User first name
        last_name: User last name
        role: User role
        phone_number: Optional phone number
        **kwargs: Additional user fields
        
    Returns:
        Created User object
    """
    # Check if email already exists
    result = await db.execute(
        select(User).where(User.email == email)
    )
    existing = result.scalar_one_or_none()
    
    if existing:
        raise ValueError(f"User with email {email} already exists")
    
    user = User(
        email=email,
        password_hash=get_password_hash(password),
        first_name=first_name,
        last_name=last_name,
        role=role,
        phone_number=phone_number,
        verification_status=VerificationStatus.PENDING,
        **kwargs
    )
    
    db.add(user)
    await db.commit()
    await db.refresh(user)
    
    return user


class TokenData:
    """Data class for JWT token payload"""
    def __init__(
        self,
        user_id: str,
        email: str,
        role: str,
        exp: datetime = None
    ):
        self.user_id = user_id
        self.email = email
        self.role = role
        self.exp = exp
    
    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "TokenData":
        return cls(
            user_id=payload.get("sub"),
            email=payload.get("email"),
            role=payload.get("role"),
            exp=payload.get("exp")
        )
