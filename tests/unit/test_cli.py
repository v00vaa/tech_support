"""Tests for database bootstrap and demonstration CLI commands."""

from sqlalchemy import inspect

from app.extensions import db
from app.models import Client, Dialog, Employee, Role


def test_init_db_command_creates_tables(app) -> None:
    result = app.test_cli_runner().invoke(args=["init-db"])

    assert result.exit_code == 0
    assert "База данных инициализирована" in result.output
    with app.app_context():
        assert inspect(db.engine).has_table("employees")
        assert inspect(db.engine).has_table("roles")


def test_bootstrap_creates_first_administrator_and_is_idempotent(app) -> None:
    runner = app.test_cli_runner()
    initialized = runner.invoke(args=["init-db"])
    assert initialized.exit_code == 0

    first_run = runner.invoke(
        args=["bootstrap"],
        input="bootstrap-admin@example.com\nBootstrap-password-123!\nBootstrap-password-123!\n",
    )
    assert first_run.exit_code == 0
    assert "учетная запись администратора готова" in first_run.output.lower()
    assert "потребуется сменить" in first_run.output.lower()

    with app.app_context():
        administrator = db.session.scalar(
            db.select(Employee).where(Employee.email == "bootstrap-admin@example.com")
        )
        assert administrator is not None
        assert administrator.must_change_password is True
        assert administrator.check_password("Bootstrap-password-123!")
        assert any(role.code == "administrator" for role in administrator.roles)

    second_run = runner.invoke(
        args=["bootstrap"],
        input="bootstrap-admin@example.com\n",
    )
    assert second_run.exit_code == 0
    assert "потребуется сменить" not in second_run.output.lower()


def test_bootstrap_rejects_short_temporary_password(app) -> None:
    runner = app.test_cli_runner()
    assert runner.invoke(args=["init-db"]).exit_code == 0

    result = runner.invoke(
        args=["bootstrap"],
        input="short-password-admin@example.com\nshort\nshort\n",
    )

    assert isinstance(result.exception, SystemExit)
    assert result.exit_code != 0
    assert "не менее 8 символов" in result.output


def test_bootstrap_rejects_disabled_administrator_account(app) -> None:
    runner = app.test_cli_runner()
    assert runner.invoke(args=["init-db"]).exit_code == 0

    created = runner.invoke(
        args=["bootstrap"],
        input="disabled-admin@example.com\nDisabled-password-123!\nDisabled-password-123!\n",
    )
    assert created.exit_code == 0

    with app.app_context():
        administrator = db.session.scalar(
            db.select(Employee).where(Employee.email == "disabled-admin@example.com")
        )
        assert administrator is not None
        administrator.is_active = False
        db.session.commit()

    result = runner.invoke(
        args=["bootstrap"],
        input="disabled-admin@example.com\n",
    )
    assert result.exit_code != 0
    assert "отключена" in result.output


def test_auto_forward_worker_exposes_interval_and_batch_options(app) -> None:
    result = app.test_cli_runner().invoke(args=["run-auto-forward-worker", "--help"])

    assert result.exit_code == 0
    assert "--interval" in result.output
    assert "--batch-size" in result.output
    assert "--moderation-batch-size" in result.output


def test_seed_command_creates_demo_data_and_can_run_twice(app) -> None:
    runner = app.test_cli_runner()
    assert runner.invoke(args=["init-db"]).exit_code == 0

    first_run = runner.invoke(
        args=["seed"],
        input="Demo-agent-password-123!\n",
    )
    assert first_run.exit_code == 0
    assert "демонстрационные данные подготовлены" in first_run.output.lower()

    with app.app_context():
        assert (
            db.session.scalar(db.select(Employee).where(Employee.email == "anna@example.com"))
            is not None
        )
        assert (
            db.session.scalar(db.select(Client).where(Client.email == "ivan@example.com"))
            is not None
        )
        assert (
            db.session.scalar(
                db.select(Dialog).where(Dialog.subject == "Не работает личный кабинет")
            )
            is not None
        )
        assert db.session.scalar(db.select(Role).where(Role.code == "support_level_1")) is not None

    second_run = runner.invoke(args=["seed"])
    assert second_run.exit_code == 0
    assert "демонстрационные данные подготовлены" in second_run.output.lower()


def test_auto_forward_worker_stops_gracefully_on_sigterm(app, monkeypatch) -> None:
    import app.core.cli as cli_module

    registered_handlers = {}
    original_handlers = {}
    restored_handlers = []
    processed_batches = []

    class FakeEvent:
        stopped = False

        def is_set(self) -> bool:
            return self.stopped

        def set(self) -> None:
            self.stopped = True

        def wait(self, timeout: int) -> bool:
            assert timeout == 5
            registered_handlers[cli_module.signal.SIGTERM](cli_module.signal.SIGTERM, None)
            return self.stopped

    def fake_signal(signum, handler):
        original = original_handlers.setdefault(signum, object())
        if handler is original:
            restored_handlers.append(signum)
        else:
            registered_handlers[signum] = handler
        return original

    monkeypatch.setattr(cli_module, "Event", FakeEvent)
    monkeypatch.setattr(cli_module.signal, "signal", fake_signal)
    monkeypatch.setattr(
        cli_module,
        "process_due_auto_forwards",
        lambda *, limit: processed_batches.append(limit) or 0,
    )
    monkeypatch.setattr(cli_module, "process_pending_moderation", lambda *, limit: 0)

    result = app.test_cli_runner().invoke(
        args=["run-auto-forward-worker", "--interval", "5", "--batch-size", "7"]
    )

    assert result.exit_code == 0
    assert processed_batches == [7]
    assert set(restored_handlers) == {cli_module.signal.SIGINT, cli_module.signal.SIGTERM}
