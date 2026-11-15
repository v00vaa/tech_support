"""Shared pytest fixtures."""

from collections.abc import Iterator

import pytest
from flask import Flask

from app import create_app
from app.core.config import Settings
from app.extensions import db
from app.models import Client


@pytest.fixture
def app() -> Iterator[Flask]:
    application = create_app(
        Settings(
            database_url="sqlite+pysqlite:///:memory:",
            environment="testing",
        )
    )
    application.config.update(TESTING=True)

    yield application

    # Flask-SQLAlchemy requires an active application context.
    with application.app_context():
        application.extensions["sqlalchemy"].engine.dispose()


@pytest.fixture
def client(app: Flask):  # type: ignore[no-untyped-def]
    return app.test_client()


@pytest.fixture
def customer_records(app: Flask) -> Iterator[int]:
    """Create one customer account for password-recovery tests."""
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        db.create_all()
        customer = Client(
            name="Password Reset Customer",
            login="customer-one",
            email="one@example.com",
        )
        customer.set_password("correct-horse-battery")
        db.session.add(customer)
        db.session.commit()
        customer_id = customer.id

        yield customer_id

        db.session.remove()
        db.drop_all()
