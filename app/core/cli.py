"""Flask CLI commands for a ready-to-demo database."""

import click
from flask import Flask

from app.extensions import db
from app.models import AuthorType, Client, Dialog, DialogStatus, Employee
from app.services import dialog_service, message_service


def register_commands(app: Flask) -> None:
    @app.cli.command("init-db")
    def init_db() -> None:
        """Create all tables for local development."""
        db.create_all()
        click.echo("База данных инициализирована.")

    @app.cli.command("seed")
    def seed() -> None:
        """Create a small idempotent demonstration dataset."""
        db.create_all()
        if db.session.scalar(db.select(Employee).limit(1)):
            click.echo("Демонстрационные данные уже существуют.")
            return
        from app.core.config import get_settings

        settings = get_settings()
        admin = Employee(name="Администратор", email=settings.admin_email, position="Администратор", password_hash="")
        admin.set_password(settings.admin_password)
        specialist = Employee(name="Анна Петрова", email="anna@example.com", position="Специалист поддержки", password_hash="")
        specialist.set_password("support123")
        client_one = Client(name="Иван Иванов", email="ivan@example.com", phone="+7 900 000-00-01")
        client_two = Client(name="ООО Ромашка", email="office@romashka.example", phone="+7 900 000-00-02")
        db.session.add_all([admin, specialist, client_one, client_two])
        db.session.commit()
        dialog = dialog_service.create_dialog(client_one.id, specialist.id, "Не работает личный кабинет", "Web")
        dialog_service.change_status(dialog, DialogStatus.IN_PROGRESS)
        message_service.create_message(dialog.id, AuthorType.CLIENT, client_one.id, "Не могу войти в личный кабинет.")
        message_service.create_message(dialog.id, AuthorType.EMPLOYEE, specialist.id, "Проверяю информацию по вашему аккаунту.")
        click.echo("Демонстрационные данные созданы.")
