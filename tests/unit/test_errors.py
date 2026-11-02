"""Tests for browser and JSON exception handlers."""

from flask import Flask

from app.core.errors import register_error_handlers


def test_browser_not_found_uses_html_template(app: Flask) -> None:
    response = app.test_client().get("/route-that-does-not-exist")

    assert response.status_code == 404
    assert b"404" in response.data


def test_unexpected_browser_error_uses_generic_error_page(app: Flask) -> None:
    app.config["PROPAGATE_EXCEPTIONS"] = False

    def fail() -> None:
        raise RuntimeError("private implementation detail")

    app.add_url_rule("/test-unexpected-error", view_func=fail)
    response = app.test_client().get("/test-unexpected-error")

    assert response.status_code == 500
    assert b"500" in response.data
    assert b"private implementation detail" not in response.data


def test_unexpected_api_error_returns_generic_json(app: Flask) -> None:
    app.config["PROPAGATE_EXCEPTIONS"] = False

    def fail() -> None:
        raise RuntimeError("private implementation detail")

    app.add_url_rule("/api/v1/test-unexpected-error", view_func=fail)
    response = app.test_client().get("/api/v1/test-unexpected-error")

    assert response.status_code == 500
    assert response.json == {
        "error": {
            "code": "internal_error",
            "message": "Internal server error",
        }
    }


def test_error_handlers_can_be_registered_on_existing_app(app: Flask) -> None:
    register_error_handlers(app)

    response = app.test_client().get("/missing")

    assert response.status_code == 404
