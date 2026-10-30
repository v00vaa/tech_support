"""HTTP-only error mapping."""

from typing import Any

from flask import Flask, jsonify
from werkzeug.exceptions import HTTPException


def register_error_handlers(app: Flask) -> None:
    """Return API-safe JSON errors without leaking implementation details."""

    @app.errorhandler(HTTPException)
    def handle_http_error(error: HTTPException) -> tuple[Any, int]:
        return jsonify(error={"code": error.name, "message": error.description}), error.code or 500

    @app.errorhandler(Exception)
    def handle_unexpected_error(_: Exception) -> tuple[Any, int]:
        app.logger.exception("Unhandled application error")
        return jsonify(error={"code": "internal_error", "message": "Internal server error"}), 500
