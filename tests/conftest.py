"""Shared pytest fixtures."""

from collections.abc import Iterator

import pytest
from flask import Flask

from app import create_app
from app.core.config import Settings


@pytest.fixture
def app() -> Iterator[Flask]:
    application = create_app(
        Settings(database_url="sqlite+pysqlite:///:memory:", environment="testing")
    )
    application.config.update(TESTING=True)
    yield application
    application.extensions["database"].engine.dispose()


@pytest.fixture
def client(app: Flask):  # type: ignore[no-untyped-def]
    return app.test_client()
