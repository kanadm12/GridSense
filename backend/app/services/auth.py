"""Authentication service for password hashing and JWT tokens."""

from datetime import datetime, timedelta, timezone
import uuid

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.user import User
from app.schemas.auth import TokenData, UserCreate

settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthService:
    """Service for authentication operations."""

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verify a password against a hash."""
        return pwd_context.verify(plain_password, hashed_password)

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a password."""
        return pwd_context.hash(password)

    @staticmethod
    def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
        """Create a JWT access token."""
        to_encode = data.copy()
        expire = datetime.now(timezone.utc) + (
            expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
        )
        to_encode.update({"exp": expire, "type": "access"})
        return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)

    @staticmethod
    def create_refresh_token(data: dict) -> str:
        """Create a JWT refresh token with longer expiry."""
        to_encode = data.copy()
        now = datetime.now(timezone.utc)
        expire = now + timedelta(days=settings.refresh_token_expire_days)
        to_encode.update({
            "exp": expire,
            "type": "refresh",
            "iat": int(now.timestamp()),
            "jti": uuid.uuid4().hex,
        })
        return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)

    @staticmethod
    def decode_token(token: str, expected_type: str = "access") -> TokenData | None:
        """Decode and validate a JWT token."""
        try:
            payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
            user_id: int | None = payload.get("sub")
            token_type: str = payload.get("type", "access")
            
            if user_id is None:
                return None
            if token_type != expected_type:
                return None
                
            return TokenData(user_id=int(user_id), token_type=token_type)
        except JWTError:
            return None

    @staticmethod
    def refresh_access_token(refresh_token: str) -> tuple[str, str] | None:
        """Create new access and refresh tokens from a valid refresh token.
        
        Returns tuple of (access_token, refresh_token) or None if invalid.
        """
        token_data = AuthService.decode_token(refresh_token, expected_type="refresh")
        if not token_data or not token_data.user_id:
            return None
        
        # Create new tokens
        new_access = AuthService.create_access_token(data={"sub": str(token_data.user_id)})
        new_refresh = AuthService.create_refresh_token(data={"sub": str(token_data.user_id)})
        
        return (new_access, new_refresh)

    @staticmethod
    def get_user_by_email(db: Session, email: str) -> User | None:
        """Get a user by email."""
        return db.query(User).filter(User.email == email).first()

    @staticmethod
    def get_user_by_id(db: Session, user_id: int) -> User | None:
        """Get a user by ID."""
        return db.query(User).filter(User.id == user_id).first()

    @staticmethod
    def create_user(db: Session, user_data: UserCreate) -> User:
        """Create a new user."""
        hashed_password = AuthService.hash_password(user_data.password)
        user = User(
            email=user_data.email,
            hashed_password=hashed_password,
            full_name=user_data.full_name,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def authenticate_user(db: Session, email: str, password: str) -> User | None:
        """Authenticate a user with email and password."""
        user = AuthService.get_user_by_email(db, email)
        if not user:
            return None
        if not AuthService.verify_password(password, user.hashed_password):
            return None
        return user
