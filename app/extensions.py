"""Flask extensions shared by the application."""

from typing import Any, cast

from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models."""


db: SQLAlchemy = SQLAlchemy(model_class=Base)
migrate: Migrate = Migrate()
login_manager: LoginManager = LoginManager()

cast(Any, login_manager).login_view = "auth.login"
login_manager.login_message = "Войдите, чтобы продолжить работу."
login_manager.login_message_category = "warning"