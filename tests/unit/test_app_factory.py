"""Tests for application composition."""

from flask import Flask

from app import create_app
from app.core.config import Settings


def test_create_app_registers_transport_and_database() -> None:
    app = create_app(
        Settings(
            database_url="sqlite+pysqlite:///:memory:",
            environment="testing",
        )
    )

    try:
        assert isinstance(app, Flask)
        assert "sqlalchemy" in app.extensions
        assert "database" in app.extensions
        assert "api.liveness" in app.view_functions
    finally:
        with app.app_context():
            app.extensions["database"].engine.dispose()