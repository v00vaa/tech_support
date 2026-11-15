"""Short-lived, password-bound customer password-reset tokens and email delivery."""

from __future__ import annotations

import hashlib
import hmac
import smtplib
from email.message import EmailMessage
from typing import Callable
from urllib.parse import urljoin

from flask import current_app, url_for
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.models.client import Client


class InvalidPasswordResetToken(ValueError):
    """The reset token is invalid, expired, or no longer applicable."""


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="client-password-reset-v1")


def _password_fingerprint(client: Client) -> str:
    password_hash = client.password_hash or ""
    return hmac.new(
        current_app.config["SECRET_KEY"].encode("utf-8"),
        password_hash.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def generate_password_reset_token(client: Client) -> str:
    """Create a token invalidated automatically by any password change."""
    return _serializer().dumps({"client_id": client.id, "password": _password_fingerprint(client)})


def verify_password_reset_token(token: str, *, max_age: int) -> Client:
    """Validate signature, age, account state, and current password fingerprint."""
    try:
        payload = _serializer().loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired) as error:
        raise InvalidPasswordResetToken from error
    if not isinstance(payload, dict) or not isinstance(payload.get("client_id"), int):
        raise InvalidPasswordResetToken
    client = Client.query.get(payload["client_id"])
    if (
        client is None
        or not client.is_active
        or not client.password_hash
        or not isinstance(payload.get("password"), str)
        or not hmac.compare_digest(payload["password"], _password_fingerprint(client))
    ):
        raise InvalidPasswordResetToken
    return client


def send_password_reset_email(client: Client, token: str) -> None:
    """Send a reset link using SMTP; tests may inject a sender callback."""
    injected: Callable[[str, str, str], None] | None = current_app.config.get(
        "PASSWORD_RESET_EMAIL_SENDER"
    )
    reset_url = urljoin(
        current_app.config["PUBLIC_BASE_URL"].rstrip("/") + "/",
        url_for("client_password_reset.reset_password", token=token).lstrip("/"),
    )
    subject = "Восстановление пароля Support Desk"
    body = (
        f"Здравствуйте, {client.name}!\n\n"
        "Для задания нового пароля перейдите по ссылке (она действует 30 минут):\n"
        f"{reset_url}\n\n"
        "Если вы не запрашивали восстановление, просто проигнорируйте это письмо."
    )
    if injected is not None:
        injected(client.email or "", subject, body)
        return

    host = current_app.config.get("SMTP_HOST")
    sender = current_app.config.get("SMTP_SENDER")
    if not host or not sender or not client.email:
        raise RuntimeError("Password-reset email delivery is not configured")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = client.email
    message.set_content(body)
    port = current_app.config["SMTP_PORT"]
    timeout = current_app.config["SMTP_TIMEOUT_SECONDS"]
    with smtplib.SMTP(host, port, timeout=timeout) as smtp:
        if current_app.config["SMTP_USE_TLS"]:
            smtp.starttls()
        username = current_app.config.get("SMTP_USERNAME")
        password = current_app.config.get("SMTP_PASSWORD")
        if username and password:
            smtp.login(username, password)
        smtp.send_message(message)
