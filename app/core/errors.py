"""Browser-friendly error pages."""

from flask import Flask, render_template


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(404)
    def not_found(_: object) -> tuple[str, int]:
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def internal_error(_: object) -> tuple[str, int]:
        return render_template("errors/500.html"), 500
