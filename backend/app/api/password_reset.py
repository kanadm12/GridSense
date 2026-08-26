"""Password reset endpoints."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models.password_reset import PasswordResetToken
from app.models.user import User
from app.services.auth import AuthService
from app.services.email import get_email_provider

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _is_expired(expires_at: datetime) -> bool:
    """Compare reset expiry timestamps consistently across database backends."""
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) > expires_at


class ForgotPasswordRequest(BaseModel):
    """Request body for forgot password."""

    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """Request body for reset password."""

    token: str
    new_password: str


@router.post("/forgot-password")
async def forgot_password(
    request: ForgotPasswordRequest,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Request a password reset email.

    Always returns success to prevent email enumeration attacks.
    """
    user = AuthService.get_user_by_email(db, request.email)

    if user:
        # Invalidate any existing tokens
        db.query(PasswordResetToken).filter(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used.is_(False),
        ).update({"used": True})

        # Create new token
        token = secrets.token_urlsafe(32)
        reset_token = PasswordResetToken(
            user_id=user.id,
            token=hashlib.sha256(token.encode()).hexdigest(),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        db.add(reset_token)
        db.commit()

        settings = get_settings()
        reset_url = f"{settings.frontend_reset_url}?token={token}"
        try:
            await get_email_provider(settings).send_password_reset(request.email, reset_url)
        except Exception:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Password reset service is temporarily unavailable.",
            )

    # Always return success (security best practice)
    return {"message": "If that email exists, a password reset link has been sent."}


@router.post("/reset-password")
async def reset_password(
    request: ResetPasswordRequest,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Reset password using a valid token."""
    # Find the token
    reset_token = (
        db.query(PasswordResetToken)
        .filter(
            PasswordResetToken.token == hashlib.sha256(request.token.encode()).hexdigest(),
            PasswordResetToken.used.is_(False),
        )
        .first()
    )

    if not reset_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token.",
        )

    # Check expiration
    if _is_expired(reset_token.expires_at):
        reset_token.used = True
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset token has expired. Please request a new one.",
        )

    # Validate password
    if len(request.new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters.",
        )

    # Update password
    user = db.query(User).filter(User.id == reset_token.user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    user.hashed_password = AuthService.hash_password(request.new_password)
    reset_token.used = True
    db.commit()

    return {"message": "Password has been reset successfully. You can now log in."}


@router.post("/verify-reset-token")
async def verify_reset_token(
    token: str,
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    """Verify if a reset token is valid (used by frontend)."""
    reset_token = (
        db.query(PasswordResetToken)
        .filter(
            PasswordResetToken.token == hashlib.sha256(token.encode()).hexdigest(),
            PasswordResetToken.used.is_(False),
        )
        .first()
    )

    if not reset_token:
        return {"valid": False}

    if _is_expired(reset_token.expires_at):
        return {"valid": False}

    return {"valid": True}
