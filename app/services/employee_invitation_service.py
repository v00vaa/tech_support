"""Secure employee invitation lifecycle and email delivery."""

from __future__ import annotations

import hashlib
import secrets
import smtplib
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from urllib.parse import urljoin

from flask import current_app, url_for
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash

from app.extensions import db
from app.models.employee import Employee
from app.models.employee_invitation import EmployeeInvitation
from app.models.role import Role


class InvalidEmployeeInvitation(ValueError):
    """Invitation is unknown, expired, revoked, or already accepted."""


class EmployeeInvitationConflict(ValueError):
    """An employee account already exists for the invitation email."""


def _token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_employee_invitation(
    *,
    email: str,
    name: str,
    position: str,
    invited_by_employee_id: int,
    role_id: int,
    lifetime_hours: int = 72,
) -> tuple[EmployeeInvitation, str]:
    """Persist a new invitation and invalidate earlier pending invitations."""
    normalized_email = email.strip().casefold()
    existing_employee = db.session.scalar(
        select(Employee.id).where(func.lower(Employee.email) == normalized_email)
    )
    if existing_employee is not None:
        raise EmployeeInvitationConflict("Сотрудник с таким email уже существует.")

    role = db.session.get(Role, role_id)
    if (
        role is None
        or not role.is_active
        or role.role_type != "MAIN"
        or role.code == "administrator"
    ):
        raise ValueError("Для приглашения выберите активную основную роль.")

    now = datetime.now(UTC)
    previous = db.session.scalars(
        select(EmployeeInvitation).where(
            func.lower(EmployeeInvitation.email) == normalized_email,
            EmployeeInvitation.accepted_at.is_(None),
            EmployeeInvitation.revoked_at.is_(None),
        )
    ).all()
    for invitation in previous:
        invitation.revoked_at = now

    token = secrets.token_urlsafe(32)
    invitation = EmployeeInvitation(
        email=normalized_email,
        name=name.strip(),
        position=position.strip(),
        token_hash=_token_digest(token),
        expires_at=now + timedelta(hours=lifetime_hours),
        invited_by_employee_id=invited_by_employee_id,
        role_id=role.id,
        created_at=now,
    )
    db.session.add(invitation)
    db.session.commit()
    return invitation, token


def send_employee_invitation_email(invitation: EmployeeInvitation, token: str) -> None:
    """Deliver a one-time invitation link using the configured SMTP transport."""
    injected: Callable[[str, str, str], None] | None = current_app.config.get(
        "EMPLOYEE_INVITATION_EMAIL_SENDER"
    )
    host = current_app.config.get("SMTP_HOST")
    sender = current_app.config.get("SMTP_SENDER")
    if injected is None and (not isinstance(host, str) or not isinstance(sender, str)):
        raise RuntimeError("Employee invitation email delivery is not configured")

    invitation_path = url_for("auth.accept_employee_invitation_route", token=token, _external=False)
    invitation_url = urljoin(
        current_app.config["PUBLIC_BASE_URL"].rstrip("/") + "/",
        invitation_path.lstrip("/"),
    )
    subject = "Приглашение в Support Desk"
    body = (
        f"Здравствуйте, {invitation.name}!\n\n"
        "Вас пригласили в систему технической поддержки Support Desk.\n"
        "Чтобы активировать учётную запись и задать пароль, перейдите по ссылке:\n"
        f"{invitation_url}\n\n"
        "Ссылка действует 72 часа и может быть использована только один раз. "
        "Если вы не ожидали приглашение, проигнорируйте это письмо."
    )
    if injected is not None:
        injected(invitation.email, subject, body)
        return
    if not isinstance(host, str) or not isinstance(sender, str):
        raise RuntimeError("Employee invitation email delivery is not configured")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = invitation.email
    message.set_content(body)
    with smtplib.SMTP(
        host,
        current_app.config["SMTP_PORT"],
        timeout=current_app.config["SMTP_TIMEOUT_SECONDS"],
    ) as smtp:
        if current_app.config["SMTP_USE_TLS"]:
            smtp.starttls()
        username = current_app.config.get("SMTP_USERNAME")
        password = current_app.config.get("SMTP_PASSWORD")
        if username and password:
            smtp.login(username, password)
        smtp.send_message(message)


def get_valid_employee_invitation(
    token: str,
    *,
    lock: bool = False,
) -> EmployeeInvitation:
    """Resolve an invitation without exposing its token in persistent storage."""
    statement = select(EmployeeInvitation).where(
        EmployeeInvitation.token_hash == _token_digest(token),
        EmployeeInvitation.accepted_at.is_(None),
        EmployeeInvitation.revoked_at.is_(None),
    )
    if lock:
        statement = statement.with_for_update()
    invitation = db.session.scalar(statement)
    if invitation is None:
        raise InvalidEmployeeInvitation
    expires_at = invitation.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= datetime.now(UTC):
        raise InvalidEmployeeInvitation
    return invitation


def accept_employee_invitation(token: str, password: str) -> Employee:
    """Atomically consume an invitation and create the employee account."""
    invitation = get_valid_employee_invitation(token, lock=True)
    existing_employee = db.session.scalar(
        select(Employee.id).where(func.lower(Employee.email) == invitation.email.casefold())
    )
    if existing_employee is not None:
        raise EmployeeInvitationConflict("Учётная запись с таким email уже существует.")

    role = db.session.get(Role, invitation.role_id)
    if role is None or not role.is_active or role.role_type != "MAIN":
        raise InvalidEmployeeInvitation

    employee = Employee(
        name=invitation.name,
        email=invitation.email,
        position=invitation.position,
        password_hash=generate_password_hash(password),
        is_active=True,
        must_change_password=False,
        roles=[role],
    )
    invitation.accepted_at = datetime.now(UTC)
    db.session.add(employee)
    try:
        db.session.commit()
    except IntegrityError as error:
        db.session.rollback()
        raise EmployeeInvitationConflict("Учётная запись с таким email уже существует.") from error
    return employee


def revoke_employee_invitation(invitation: EmployeeInvitation) -> None:
    """Revoke an invitation under a row lock so acceptance cannot race the revocation."""
    locked_invitation = db.session.scalar(
        select(EmployeeInvitation)
        .where(EmployeeInvitation.id == invitation.id)
        .with_for_update()
    )
    if (
        locked_invitation is None
        or locked_invitation.accepted_at is not None
        or locked_invitation.revoked_at is not None
    ):
        raise InvalidEmployeeInvitation
    locked_invitation.revoked_at = datetime.now(UTC)
    db.session.commit()
