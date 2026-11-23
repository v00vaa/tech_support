"""Flask CLI commands for database bootstrap and demo data."""

import signal
from threading import Event
from time import monotonic

import click
from flask import Flask
from werkzeug.security import generate_password_hash

from app.extensions import db
from app.models import AuthorType, Client, Dialog, DialogStatus, Employee, Role
from app.services import dialog_service, message_service
from app.services.attachment_storage_service import (
    cleanup_expired_closed_dialogs,
    remove_orphaned_attachment_files,
)
from app.services.rbac_service import ensure_rbac_catalogue
from app.services.routing_service import process_due_auto_forwards


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
        has_administrator = (
            db.session.scalar(
                db.select(Employee.id)
                .join(Employee.roles)
                .where(Employee.is_active, Role.is_active, Role.code == "administrator")
                .limit(1)
            )
            is not None
        )
        is_first_administrator = not has_administrator
        employee = db.session.scalar(db.select(Employee).where(Employee.email == email))
        if employee is None:
            password = click.prompt(
                "Временный пароль (не менее 8 символов)",
                hide_input=True,
                confirmation_prompt=True,
            )
            if len(password) < 8:
                raise click.ClickException("Пароль должен содержать не менее 8 символов.")
            employee = Employee(
                name="Администратор",
                email=email,
                position="Администратор",
                password_hash=generate_password_hash(password),
                is_active=True,
                must_change_password=True,
            )
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

    @app.cli.command("cleanup-orphaned-attachments")
    @click.option(
        "--min-age-hours",
        default=24,
        show_default=True,
        type=click.IntRange(min=1),
    )
    def cleanup_orphaned_attachments(min_age_hours: int) -> None:
        """Remove unreferenced attachment files older than the safety grace period."""
        count = remove_orphaned_attachment_files(min_age_hours)
        click.echo(f"Удалено осиротевших файлов: {count}")

    @app.cli.command("cleanup-expired-dialogs")
    @click.option("--limit", default=100, show_default=True, type=click.IntRange(min=1, max=1000))
    def cleanup_expired_dialogs_command(limit: int) -> None:
        """Delete closed dialogs and attachments after the configured retention period."""
        count = cleanup_expired_closed_dialogs(limit=limit)
        click.echo(f"Удалено обращений с истёкшим сроком хранения: {count}")

    @app.cli.command("process-auto-forwards")
    def process_auto_forwards_command() -> None:
        """Process role routes whose automatic forwarding threshold has elapsed."""
        count = process_due_auto_forwards()
        click.echo(f"Автоматически передано диалогов: {count}")

    @app.cli.command("run-auto-forward-worker")
    @click.option("--interval", default=60, show_default=True, type=click.IntRange(min=5))
    @click.option(
        "--batch-size", default=100, show_default=True, type=click.IntRange(min=1, max=1000)
    )
    def run_auto_forward_worker(interval: int, batch_size: int) -> None:
        """Run the automatic role forwarding worker until interrupted."""
        app.logger.info(
            "Worker автопередачи запущен: interval=%s batch_size=%s", interval, batch_size
        )
        stop_event = Event()

        def request_stop(signum: int, frame: object) -> None:
            del frame
            app.logger.info("Получен сигнал %s; worker завершит текущий цикл", signum)
            stop_event.set()

        previous_handlers = {
            signum: signal.signal(signum, request_stop)
            for signum in (signal.SIGINT, signal.SIGTERM)
        }
        last_retention_cleanup = 0.0
        try:
            while not stop_event.is_set():
                try:
                    count = process_due_auto_forwards(limit=batch_size)
                    if count:
                        app.logger.info("Автоматически передано обращений: %s", count)
                    now = monotonic()
                    if now - last_retention_cleanup >= 24 * 60 * 60:
                        deleted = cleanup_expired_closed_dialogs(limit=batch_size)
                        if deleted:
                            app.logger.info("Удалено обращений по сроку хранения: %s", deleted)
                        last_retention_cleanup = now
                except Exception:
                    db.session.rollback()
                    app.logger.exception("Ошибка цикла worker автопередачи")
                stop_event.wait(interval)
            app.logger.info("Worker автопередачи остановлен")
        finally:
            for signum, handler in previous_handlers.items():
                signal.signal(signum, handler)
            db.session.remove()

    @app.cli.command("seed")
    def seed() -> None:
        """Create a small demonstration dataset without default admin credentials."""
        db.create_all()
        _, support_role = ensure_rbac_catalogue()

        specialist = db.session.scalar(
            db.select(Employee).where(Employee.email == "anna@example.com")
        )
        if specialist is None:
            specialist_password = click.prompt(
                "Пароль демо-сотрудника anna@example.com", hide_input=True
            )
            specialist = Employee(
                name="Анна Петрова",
                email="anna@example.com",
                position="Специалист поддержки",
                password_hash=generate_password_hash(specialist_password),
                is_active=True,
            )
            specialist.roles = [support_role]
            db.session.add(specialist)
            db.session.flush()

        client_one = db.session.scalar(db.select(Client).where(Client.email == "ivan@example.com"))
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
            db.session.add(
                Client(
                    name="ООО Ромашка",
                    email="office@romashka.example",
                    phone="+7 900 000-00-02",
                )
            )

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
                dialog.id,
                AuthorType.CLIENT,
                client_one.id,
                "Не могу войти в личный кабинет.",
            )
            message_service.create_message(
                dialog.id,
                AuthorType.EMPLOYEE,
                specialist.id,
                "Проверяю информацию по вашему аккаунту.",
            )
        click.echo("Демонстрационные данные подготовлены.")
