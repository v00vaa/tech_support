"""Tests for transport health checks."""

from unittest.mock import patch

from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy.exc import SQLAlchemyError


def test_liveness_returns_ok(client: FlaskClient) -> None:
    response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json == {"status": "ok"}


def test_readiness_returns_ok_with_available_database(client: FlaskClient) -> None:
    response = client.get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json == {"status": "ok"}


def test_readiness_returns_service_unavailable_when_database_is_down(app: Flask) -> None:
    database = app.extensions["database"]
    with patch.object(database.engine, "connect", side_effect=SQLAlchemyError()):
        response = app.test_client().get("/api/v1/health/ready")

    assert response.status_code == 503
    assert response.json == {"status": "not_ready"}


def test_http_errors_are_returned_as_json(client: FlaskClient) -> None:
    response = client.get("/does-not-exist")

    assert response.status_code == 404
    assert response.json is not None
    assert response.json["error"]["code"] == "Not Found"
