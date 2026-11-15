"""Unit tests for password-reset token validation and SMTP delivery."""

from unittest.mock import MagicMock, patch

import pytest
from itsdangerous import URLSafeTimedSerializer

from app.extensions import db
from app.models import Client
from app.services.password_reset_service import (
    InvalidPasswordResetToken,
    generate_password_reset_token,
    send_password_reset_email,
    verify_password_reset_token,
)


def _customer() -> Client:
    customer = Client(
        name="Reset Service Customer",
        login="reset-service",
        email="reset@example.com",
    )
    customer.set_password("original-password-long")
    db.session.add(customer)
    db.session.commit()
    return customer


def test_verification_rejects_malformed_expired_and_unknown_customer_tokens(app):
    with app.app_context():
        db.create_all()
        customer = _customer()

        with pytest.raises(InvalidPasswordResetToken):
            verify_password_reset_token("not-a-signed-token", max_age=1800)

        token = generate_password_reset_token(customer)
        with pytest.raises(InvalidPasswordResetToken):
            verify_password_reset_token(token, max_age=0)

        unknown_token = URLSafeTimedSerializer(
            app.config["SECRET_KEY"], salt="client-password-reset-v1"
        ).dumps({"client_id": 99999, "password": "fingerprint"})
        with pytest.raises(InvalidPasswordResetToken):
            verify_password_reset_token(unknown_token, max_age=1800)


def test_verification_rejects_inactive_customer(app):
    with app.app_context():
        db.create_all()
        customer = _customer()
        token = generate_password_reset_token(customer)
        customer.is_active = False
        db.session.commit()

        with pytest.raises(InvalidPasswordResetToken):
            verify_password_reset_token(token, max_age=1800)


def test_smtp_delivery_uses_tls_and_optional_authentication(app):
    with app.app_context():
        db.create_all()
        customer = _customer()
        app.config.update(
            SMTP_HOST="smtp.example.test",
            SMTP_PORT=587,
            SMTP_SENDER="support@example.test",
            SMTP_USE_TLS=True,
            SMTP_USERNAME="smtp-user",
            SMTP_PASSWORD="smtp-password",
            SMTP_TIMEOUT_SECONDS=3,
            PASSWORD_RESET_EMAIL_SENDER=None,
        )
        smtp = MagicMock()
        smtp_factory = MagicMock(return_value=smtp)
        smtp_context = smtp.__enter__.return_value
        with patch("app.services.password_reset_service.smtplib.SMTP", smtp_factory):
            send_password_reset_email(customer, "signed-token")

        smtp_factory.assert_called_once_with("smtp.example.test", 587, timeout=3)
        smtp_context.starttls.assert_called_once_with()
        smtp_context.login.assert_called_once_with("smtp-user", "smtp-password")
        smtp_context.send_message.assert_called_once()
        message = smtp_context.send_message.call_args.args[0]
        assert message["To"] == "reset@example.com"
        assert "signed-token" in message.get_content()


def test_smtp_delivery_skips_authentication_when_credentials_absent(app):
    with app.app_context():
        db.create_all()
        customer = _customer()
        app.config.update(
            SMTP_HOST="smtp.example.test",
            SMTP_SENDER="support@example.test",
            SMTP_USE_TLS=False,
            SMTP_USERNAME=None,
            SMTP_PASSWORD=None,
            PASSWORD_RESET_EMAIL_SENDER=None,
        )
        smtp = MagicMock()
        smtp_context = smtp.__enter__.return_value
        with patch("app.services.password_reset_service.smtplib.SMTP", return_value=smtp):
            send_password_reset_email(customer, "signed-token")

        smtp_context.starttls.assert_not_called()
        smtp_context.login.assert_not_called()
        smtp_context.send_message.assert_called_once()


def test_smtp_delivery_requires_host_sender_and_customer_email(app):
    with app.app_context():
        db.create_all()
        customer = _customer()
        app.config.update(
            SMTP_HOST=None,
            SMTP_SENDER=None,
            PASSWORD_RESET_EMAIL_SENDER=None,
        )
        with pytest.raises(RuntimeError, match="not configured"):
            send_password_reset_email(customer, "signed-token")
