"""Tests for password reset email providers."""

from unittest.mock import MagicMock, patch

import pytest

from app.config import Settings
from app.services.email import LocalEmailProvider, SMTPEmailProvider, get_email_provider


@pytest.mark.asyncio
async def test_local_provider_does_not_send_email():
    provider = LocalEmailProvider()

    await provider.send_password_reset("user@example.com", "gridsense://reset-password?token=token")


@pytest.mark.asyncio
async def test_smtp_provider_sends_reset_link():
    settings = Settings(
        debug=True,
        email_provider="smtp",
        email_from="GridSense <no-reply@example.com>",
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_username="mailer",
        smtp_password="password",
    )
    smtp_client = MagicMock()
    smtp_client.__enter__.return_value = smtp_client

    with patch("app.services.email.smtplib.SMTP", return_value=smtp_client):
        await SMTPEmailProvider(settings).send_password_reset(
            "user@example.com", "https://app.example.com/reset-password?token=token"
        )

    smtp_client.starttls.assert_called_once()
    smtp_client.login.assert_called_once_with("mailer", "password")
    smtp_client.send_message.assert_called_once()
    message = smtp_client.send_message.call_args.args[0]
    assert message["To"] == "user@example.com"
    assert "reset-password?token=token" in message.get_content()


def test_email_provider_selects_smtp_when_configured():
    settings = Settings(debug=True, email_provider="smtp", smtp_host="smtp.example.com")

    assert isinstance(get_email_provider(settings), SMTPEmailProvider)
