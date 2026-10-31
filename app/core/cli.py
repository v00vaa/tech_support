"""Flask CLI commands for database bootstrap and demo data."""

import click
from flask import Flask

from app.extensions import db
from app.models import AuthorType, Client, Dialog, DialogStatus, Employee, Role
from app.services import dialog_service, message_service
from app.services.rbac_service import ensure_rbac_catalogue


def register_commands(app: Flask) -> None:
    @app.cli.command("init-db")
    def init_db() -> None:
        """Create all tables for local development."""
        db.create_all()
        click.echo("База данных инициализирована.")

    @app.cli.command("bootstrap")
    def bootstrap() -> None:
        """Create built-in roles and the first administrator account."""
        from app.core.config import get_settings

        administrator_role, _ = ensure_rbac_catalogue()
        settings = get_settings()
        email = click.prompt("Email администратора", default=settings.admin_email)
        has_administrator = db.session.scalar(
            db.select(Employee.id)
            .join(Employee.roles)
            .where(Role.code == "administrator")
            .limit(1)
        ) is not None
        is_first_administrator = not has_administrator
        employee = db.session.scalar(db.select(Employee).where(Employee.email == email))
        if employee is None:
            password = click.prompt(
                "Временный пароль (не менее 12 символов)",
                hide_input=True,
                confirmation_prompt=True,
            )
            if len(password) < 12:
                raise click.ClickException("Пароль должен содержать не менее 12 символов.")
            employee = Employee(
                name="Администратор",
                email=email,
                position="Администратор",
                password_hash="",
                is_active=True,
                must_change_password=True,
            )
            employee.set_password(password)
            db.session.add(employee)
        elif not employee.is_active:
            raise click.ClickException("Учетная запись администратора отключена.")

        employee.roles = list({*employee.roles, administrator_role})
        if is_first_administrator:
            employee.must_change_password = True
        db.session.commit()
        click.echo("RBAC настроен. Учетная запись администратора готова.")
        if is_first_administrator:
            click.echo("При первом входе потребуется сменить временный пароль.")

    @app.cli.command("seed")
    def seed() -> None:
        """Create a small demonstration dataset without default admin credentials."""
        db.create_all()
        _, support_role = ensure_rbac_catalogue()

        specialist = db.session.scalar(
            db.select(Employee).where(Employee.email == "anna@example.com")
        )
        if specialist is None:
            specialist = Employee(
                name="Анна Петрова",
                email="anna@example.com",
                position="Специалист поддержки",
                password_hash="",
                is_active=True,
            )
            specialist.set_password(click.prompt(
                "Пароль демо-сотрудника anna@example.com", hide_input=True
            ))
            specialist.roles = [support_role]
            db.session.add(specialist)
            db.session.flush()

        client_one = db.session.scalar(
            db.select(Client).where(Client.email == "ivan@example.com")
        )
        if client_one is None:
            client_one = Client(
                name="Иван Иванов", email="ivan@example.com", phone="+7 900 000-00-01"
            )
            db.session.add(client_one)
            db.session.flush()

        client_two = db.session.scalar(
            db.select(Client).where(Client.email == "office@romashka.example")
        )
        if client_two is None:
            db.session.add(Client(
                name="ООО Ромашка", email="office@romashka.example",
                phone="+7 900 000-00-02",
            ))

        db.session.commit()
        existing_dialog = db.session.scalar(
            db.select(Dialog).where(Dialog.subject == "Не работает личный кабинет")
        )
        if existing_dialog is None:
            dialog = dialog_service.create_dialog(
                client_one.id, specialist.id, "Не работает личный кабинет", "Web"
            )
            dialog_service.change_status(dialog, DialogStatus.IN_PROGRESS)
            message_service.create_message(
                dialog.id, AuthorType.CLIENT, client_one.id,
                "Не могу войти в личный кабинет.",
            )
            message_service.create_message(
                dialog.id, AuthorType.EMPLOYEE, specialist.id,
                "Проверяю информацию по вашему аккаунту.",
            )
        click.echo("Демонстрационные данные подготовлены.")
