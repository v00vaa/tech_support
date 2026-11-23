"""Server-side filtering and pagination for staff directories."""

from collections.abc import Iterator

import pytest
from flask import Flask

from app.extensions import db
from app.models import Client, Employee, Role


@pytest.fixture
def directory_records(app: Flask) -> Iterator[int]:
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        db.create_all()
        admin_role = Role(
            code="administrator",
            name="Administrator",
            is_system=True,
            role_type="MAIN",
        )
        admin = Employee(
            name="Directory Admin",
            email="directory-admin@example.com",
            position="Administrator",
            password_hash="unused",
        )
        admin.roles.append(admin_role)
        db.session.add(admin)
        for index in range(30):
            client = Client(
                name=f"Customer {index:02d}",
                login=f"customer-{index:02d}",
                email=f"customer-{index:02d}@example.com",
                phone=f"+100000{index:04d}",
                external_id=f"external-{index}" if index % 2 == 0 else None,
            )
            employee = Employee(
                name=f"Employee {index:02d}",
                email=f"employee-{index:02d}@example.com",
                position="Support specialist",
                password_hash="unused",
                is_active=index % 2 == 0,
            )
            employee.roles.append(admin_role)
            db.session.add_all([client, employee])
        db.session.commit()
        admin_id = admin.id
        yield admin_id
        db.session.remove()
        db.drop_all()


@pytest.fixture
def admin_session(client, directory_records):
    with client.session_transaction() as session:
        session["_user_id"] = f"employee:{directory_records}"
        session["_fresh"] = True
    return client


def test_client_directory_search_filter_and_pagination(admin_session) -> None:
    response = admin_session.get("/clients?q=customer&linked=linked&page=2")

    assert response.status_code == 200
    assert "Найдено: 15".encode() in response.data
    assert "Страница 1 из 1".encode() in response.data
    assert b"Customer 28" in response.data
    assert b"Customer 00" in response.data


def test_client_directory_clamps_invalid_page_and_searches_phone(admin_session) -> None:
    response = admin_session.get("/clients?q=%2B1000000005&page=-10")

    assert response.status_code == 200
    assert b"Customer 05" in response.data
    assert "Найдено: 1".encode() in response.data


def test_employee_directory_filters_status_and_role(admin_session) -> None:
    response = admin_session.get("/employees?status=active&role=1&q=employee")

    assert response.status_code == 200
    assert "Найдено: 15".encode() in response.data
    assert b"Employee 00" in response.data
    assert b"Employee 01" not in response.data


def test_employee_directory_paginates_and_ignores_invalid_filters(admin_session) -> None:
    response = admin_session.get("/employees?status=unknown&role=-1&page=2")

    assert response.status_code == 200
    assert "Найдено: 30".encode() in response.data
    assert b"Employee 29" in response.data
    assert b"Employee 00" not in response.data
