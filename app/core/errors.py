"""Application error handlers for HTML pages and JSON API."""

from flask import Flask, jsonify, render_template, request
from flask.typing import ResponseReturnValue
from werkzeug.exceptions import HTTPException


def register_error_handlers(app: Flask) -> None:
    """Register handlers for browser pages and API requests."""

    @app.errorhandler(HTTPException)
    def handle_http_error(error: HTTPException) -> ResponseReturnValue:
        if request.path.startswith("/api/v1/"):
            return (
                jsonify(
                    error={
                        "code": error.name,
                        "message": error.description,
                    }
                ),
                error.code or 500,
            )

        if error.code == 404:
            return render_template("errors/404.html"), 404

        return error

    @app.errorhandler(Exception)
    def handle_unexpected_error(error: Exception) -> ResponseReturnValue:
        app.logger.exception("Unhandled application error")

        if request.path.startswith("/api/v1/"):
            return (
                jsonify(
                    error={
                        "code": "internal_error",
                        "message": "Internal server error",
                    }
                ),
                500,
            )

        return render_template("errors/500.html"), 500
