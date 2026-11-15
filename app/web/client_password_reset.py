"""Public customer password-reset endpoints."""

from flask import Blueprint, abort, current_app, flash, redirect, render_template, url_for
from flask.typing import ResponseReturnValue

from app.extensions import db, limiter
from app.models.client import Client
from app.services.password_reset_service import (
    InvalidPasswordResetToken,
    generate_password_reset_token,
    send_password_reset_email,
    verify_password_reset_token,
)
from app.web.password_reset_forms import ClientPasswordResetForm, ClientPasswordResetRequestForm

client_password_reset_bp = Blueprint("client_password_reset", __name__)


@client_password_reset_bp.route("/client/password-reset", methods=["GET", "POST"])
@limiter.limit("3 per hour")
def request_password_reset() -> ResponseReturnValue:
    """Always show the same result to avoid disclosing registered email addresses."""
    form = ClientPasswordResetRequestForm()
    if form.validate_on_submit():
        email = (form.email.data or "").strip().casefold()
        client = db.session.scalar(
            db.select(Client).where(
                Client.email.is_not(None),
                db.func.lower(Client.email) == email,
                Client.is_active.is_(True),
            )
        )
        if client is not None and client.password_hash:
            try:
                token = generate_password_reset_token(client)
                send_password_reset_email(client, token)
            except Exception:
                current_app.logger.exception(
                    "Could not send a customer password-reset email"
                )
        flash(
            "Если активный аккаунт с таким email существует, инструкция отправлена.",
            "info",
        )
        return redirect(url_for("client_password_reset.request_password_reset"))
    return render_template("auth/client_password_reset_request.html", form=form)


@client_password_reset_bp.route(
    "/client/password-reset/<string:token>", methods=["GET", "POST"]
)
@limiter.limit("10 per hour")
def reset_password(token: str) -> ResponseReturnValue:
    """Set a new password once; changing it invalidates the token."""
    try:
        client = verify_password_reset_token(
            token,
            max_age=current_app.config["PASSWORD_RESET_TOKEN_MAX_AGE"],
        )
    except InvalidPasswordResetToken:
        abort(400, description="Ссылка восстановления недействительна или устарела.")

    form = ClientPasswordResetForm()
    if form.validate_on_submit():
        client.set_password(form.password.data)
        db.session.commit()
        flash("Пароль изменен. Теперь можно войти в клиентский кабинет.", "success")
        return redirect(url_for("auth.client_login"))
    response = current_app.make_response(
        render_template("auth/client_password_reset.html", form=form)
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response
