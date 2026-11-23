"""Employee invitation management and activation tests."""

import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

from flask import Flask

from app.extensions import db
from app.models import Employee, EmployeeInvitation, Role
from app.services.employee_invitation_service import create_employee_invitation
from app.services.rbac_service import ensure_rbac_catalogue


def _new_invitation(admin_id: int, role_id: int, email: str):
    return create_employee_invitation(
        email=email,
        name="New Employee",
        position="Support specialist",
        invited_by_employee_id=admin_id,
        role_id=role_id,
    )


import pytest


@pytest.fixture
def invitation_admin(app: Flask) -> Iterator[tuple[int, int]]:
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        db.create_all()
        administrator_role, _ = ensure_rbac_catalogue()
        support_role = db.session.scalar(
            db.select(Role).where(Role.code == "support_level_1")
        )
        assert support_role is not None
        admin = Employee(
            name="Invitation Admin",
            email="invitation-admin@example.com",
            position="Administrator",
            password_hash="unused",
            roles=[administrator_role],
        )
        db.session.add(admin)
        db.session.commit()
        yield admin.id, support_role.id
        db.session.remove()
        db.drop_all()


@pytest.fixture
def admin_client(client, invitation_admin):
    with client.session_transaction() as session:
        session["_user_id"] = f"employee:{invitation_admin[0]}"
        session["_fresh"] = True
    return client


def test_admin_can_send_employee_invitation(app, admin_client, invitation_admin) -> None:
    sent: list[tuple[str, str, str]] = []
    app.config["EMPLOYEE_INVITATION_EMAIL_SENDER"] = lambda to, subject, body: sent.append(
        (to, subject, body)
    )

    response = admin_client.post(
        "/employees/invitations",
        data={
            "name": "New Specialist",
            "email": "New.Specialist@example.com",
            "position": "Support specialist",
            "role_id": str(invitation_admin[1]),
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert len(sent) == 1
    assert sent[0][0] == "new.specialist@example.com"
    token_match = re.search(r"/accept-invitation/([A-Za-z0-9_-]+)", sent[0][2])
    assert token_match is not None
    with app.app_context():
        invitation = db.session.scalar(
            db.select(EmployeeInvitation).where(
                EmployeeInvitation.email == "new.specialist@example.com"
            )
        )
        assert invitation is not None
        assert token_match.group(1) not in invitation.token_hash
        assert invitation.invited_by_employee_id == invitation_admin[0]
        assert invitation.role_id == invitation_admin[1]


def test_employee_invitation_creates_account_once(app, client, invitation_admin) -> None:
    with app.app_context():
        invitation, token = _new_invitation(*invitation_admin, "new.employee@example.com")

    response = client.post(
        f"/accept-invitation/{token}",
        data={
            "password": "a-long-and-strong-password",
            "confirm_password": "a-long-and-strong-password",
        },
    )
    assert response.status_code == 302

    with app.app_context():
        employee = db.session.scalar(
            db.select(Employee).where(Employee.email == "new.employee@example.com")
        )
        stored_invitation = db.session.get(EmployeeInvitation, invitation.id)
        assert employee is not None
        assert employee.check_password("a-long-and-strong-password")
        assert employee.is_active
        assert [role.id for role in employee.roles] == [invitation_admin[1]]
        assert stored_invitation is not None
        assert stored_invitation.accepted_at is not None

    reused = client.get(f"/accept-invitation/{token}")
    assert reused.status_code == 410


def test_expired_employee_invitation_is_rejected(app, client, invitation_admin) -> None:
    with app.app_context():
        invitation, token = _new_invitation(*invitation_admin, "expired.employee@example.com")
        invitation.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        db.session.commit()

    response = client.get(f"/accept-invitation/{token}")
    assert response.status_code == 410


def test_revoked_employee_invitation_cannot_be_used(
    app,
    admin_client,
    invitation_admin,
) -> None:
    with app.app_context():
        invitation, token = _new_invitation(*invitation_admin, "revoked.employee@example.com")
        invitation_id = invitation.id

    revoked = admin_client.post(f"/employees/invitations/{invitation_id}/revoke")
    assert revoked.status_code == 302
    assert admin_client.get(f"/accept-invitation/{token}").status_code == 410


def test_invitation_is_not_sent_when_employee_email_already_exists(
    app,
    admin_client,
    invitation_admin,
) -> None:
    sent: list[tuple[str, str, str]] = []
    app.config["EMPLOYEE_INVITATION_EMAIL_SENDER"] = lambda to, subject, body: sent.append(
        (to, subject, body)
    )
    with app.app_context():
        db.session.add(
            Employee(
                name="Existing Employee",
                email="existing@example.com",
                position="Specialist",
                password_hash="unused",
            )
        )
        db.session.commit()

    response = admin_client.post(
        "/employees/invitations",
        data={
            "name": "Duplicate",
            "email": "EXISTING@example.com",
            "position": "Specialist",
            "role_id": str(invitation_admin[1]),
        },
    )
    assert response.status_code == 200
    assert sent == []
    assert "Сотрудник с таким email уже существует.".encode() in response.data
