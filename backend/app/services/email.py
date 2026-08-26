"""Password reset email providers."""

import asyncio
import logging
import smtplib
from email.message import EmailMessage
from typing import Protocol

from app.config import Settings

logger = logging.getLogger(__name__)


class EmailProvider(Protocol):
    """Interface implemented by password reset email providers."""

    async def send_password_reset(self, recipient: str, reset_url: str) -> None:
        """Send a password reset link."""


class LocalEmailProvider:
    """Development provider that logs reset links without sending email."""

    def __init__(self, expose_link: bool = False):
        self.expose_link = expose_link

    async def send_password_reset(self, recipient: str, reset_url: str) -> None:
        if self.expose_link:
            logger.warning("Password reset link for %s: %s", recipient, reset_url)
        else:
            logger.info("Password reset email queued for %s", recipient)


class SMTPEmailProvider:
    """SMTP provider executed off the async event loop."""

    def __init__(self, settings: Settings):
        self.settings = settings

    async def send_password_reset(self, recipient: str, reset_url: str) -> None:
        await asyncio.to_thread(self._send, recipient, reset_url)

    def _send(self, recipient: str, reset_url: str) -> None:
        message = EmailMessage()
        message["Subject"] = "Reset your GridSense password"
        message["From"] = self.settings.email_from
        message["To"] = recipient
        message.set_content(
            "We received a request to reset your GridSense password.\n\n"
            f"Open this link within one hour:\n{reset_url}\n\n"
            "If you did not request this, you can ignore this email."
        )

        with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=10) as client:
            if self.settings.smtp_use_tls:
                client.starttls()
            if self.settings.smtp_username:
                client.login(self.settings.smtp_username, self.settings.smtp_password)
            client.send_message(message)


def get_email_provider(settings: Settings) -> EmailProvider:
    """Build the configured email provider."""
    if settings.email_provider == "smtp":
        return SMTPEmailProvider(settings)
    return LocalEmailProvider(expose_link=settings.debug)
