"""Tests for the standalone API error-handler registration."""

from flask import Flask, abort

from app.api.errors import register_error_handlers


def test_api_error_handler_returns_http_error_as_json():
    app = Flask(__name__)
    register_error_handlers(app)

    @app.get("/missing")
    def missing():
        abort(404, description="Not found")

    response = app.test_client().get("/missing")

    assert response.status_code == 404
    assert response.json == {"error": {"code": "Not Found", "message": "Not found"}}


def test_api_error_handler_hides_unexpected_exception():
    app = Flask(__name__)
    app.config["PROPAGATE_EXCEPTIONS"] = False
    register_error_handlers(app)

    @app.get("/failure")
    def failure():
        raise RuntimeError("sensitive implementation detail")

    response = app.test_client().get("/failure")

    assert response.status_code == 500
    assert response.json == {
        "error": {"code": "internal_error", "message": "Internal server error"}
    }
