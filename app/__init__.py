"""Application factory for the support system."""

from flask import Flask, abort, redirect, request, url_for
from flask.typing import ResponseReturnValue
from flask_login import current_user

from app.api.routes import api_bp
from app.core.config import Settings
from app.core.errors import register_error_handlers
from app.extensions import db, login_manager, migrate
from app.models.client import Client
from app.models.employee import Employee
from app.services.access_control_service import has_permission
from app.web.routes import (
    auth_bp,
    clients_bp,
    dialogs_bp,
    employees_bp,
    main_bp,
    messages_bp,
    portal_bp,
    settings_bp,
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
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=resolved_settings.environment == "production",
        REGISTRATION_PROVIDER_MODE=resolved_settings.registration_provider,
        REGISTRATION_API_BASE_URL=resolved_settings.registration_api_base_url,
        REGISTRATION_SERVICE_TOKEN=resolved_settings.registration_service_token,
        REGISTRATION_PROFILE_PATH=resolved_settings.registration_profile_path,
        REGISTRATION_REDEEM_PATH=resolved_settings.registration_redeem_path,
        REGISTRATION_TIMEOUT_SECONDS=resolved_settings.registration_timeout_seconds,
    )

    db.init_app(app)
    app.extensions["database"] = db
    migrate.init_app(app, db)
    login_manager.init_app(app)

    for blueprint in (
        main_bp,
        auth_bp,
        clients_bp,
        employees_bp,
        dialogs_bp,
        messages_bp,
        settings_bp,
        portal_bp,
        api_bp,
    ):
        app.register_blueprint(blueprint)

    @app.before_request
    def enforce_account_boundaries() -> ResponseReturnValue | None:
        if not current_user.is_authenticated:
            return None

        user = current_user._get_current_object()
        endpoint = request.endpoint or ""
        if isinstance(user, Client):
            allowed = {
                "auth.client_login",
                "auth.login",
                "auth.client_register",
                "auth.client_registration_complete",
                "auth.logout",
                "portal.index",
                "portal.dialog_create",
                "portal.dialog_detail",
                "static",
            }
            if endpoint not in allowed:
                abort(403)
            return None

        if getattr(user, "must_change_password", False) and endpoint not in {
            "auth.change_password",
            "auth.logout",
            "static",
        }:
            return redirect(url_for("auth.change_password"))
        return None

    app.jinja_env.globals["has_permission"] = has_permission

    register_error_handlers(app)
    from app.core.cli import register_commands

    register_commands(app)
    return app


@login_manager.user_loader
def load_user(user_id: str) -> Employee | Client | None:
    """Load an employee or customer using a namespaced, collision-safe identity."""
    try:
        account_type, raw_id = user_id.split(":", maxsplit=1)
        account_id = int(raw_id)
    except (AttributeError, TypeError, ValueError):
        return None

    if account_type == "employee":
        employee = db.session.get(Employee, account_id)
        return employee if employee and employee.is_active else None
    if account_type == "client":
        client = db.session.get(Client, account_id)
        return client if client and client.is_active and client.password_hash else None
    return None
