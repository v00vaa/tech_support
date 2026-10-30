"""Application factory for the support system."""

from flask import Flask, redirect, request, url_for
from flask.typing import ResponseReturnValue
from flask_login import current_user

from app.api.routes import api_bp
from app.core.config import Settings
from app.core.errors import register_error_handlers
from app.extensions import db, login_manager, migrate
from app.models.employee import Employee
from app.web.routes import (
    auth_bp, clients_bp, dialogs_bp, employees_bp, main_bp, messages_bp, settings_bp,
)


def create_app(settings: Settings | None = None) -> Flask:
    """Create and configure the Flask application."""
    resolved_settings = settings or Settings()
    app = Flask(__name__)
    app.config.update(
        DEBUG=resolved_settings.debug,
        SECRET_KEY=resolved_settings.secret_key,
        SQLALCHEMY_DATABASE_URI=resolved_settings.database_url,
        SQLALCHEMY_ECHO=resolved_settings.database_echo,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    for blueprint in (
        main_bp, auth_bp, clients_bp, employees_bp, dialogs_bp,
        messages_bp, settings_bp, api_bp,
    ):
        app.register_blueprint(blueprint)

    @app.before_request
    def require_initial_password_change() -> ResponseReturnValue | None:
        if (
            current_user.is_authenticated
            and getattr(current_user, "must_change_password", False)
            and request.endpoint not in {"auth.change_password", "auth.logout", "static"}
        ):
            return redirect(url_for("auth.change_password"))
        return None

    register_error_handlers(app)
    from app.core.cli import register_commands

    register_commands(app)
    return app


@login_manager.user_loader
def load_user(user_id: str) -> Employee | None:
    """Load an authenticated employee by their database ID."""
    try:
        employee_id = int(user_id)
    except (TypeError, ValueError):
        return None
    return db.session.get(Employee, employee_id)
