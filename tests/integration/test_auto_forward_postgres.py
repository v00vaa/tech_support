"""PostgreSQL integration tests for concurrent auto-forward workers."""

from __future__ import annotations

import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from uuid import uuid4

import pytest
from flask import Flask
from sqlalchemy import delete, event, func
from sqlalchemy.engine import make_url

from app import create_app
from app.core.config import Settings
from app.extensions import db
from app.models import AuthorType, Client, Dialog, DialogStatus, Message, Role
from app.models.role_route import RoleRoute
from app.services.routing_service import process_due_auto_forwards


@pytest.fixture
def postgres_app() -> Iterator[Flask]:
    """Use only an explicitly configured disposable PostgreSQL test database."""
    database_url = os.environ.get("SUPPORT_TEST_POSTGRES_URL")
    if not database_url:
        pytest.skip("SUPPORT_TEST_POSTGRES_URL is not configured")

    database_name = make_url(database_url).database
    if not database_name or not database_name.endswith("_test"):
        pytest.fail("SUPPORT_TEST_POSTGRES_URL must point to a database ending in _test")

    application = create_app(Settings(database_url=database_url, environment="testing"))
    with application.app_context():
        db.create_all()

    yield application

    with application.app_context():
        db.session.remove()
        db.engine.dispose()


def _create_scenario(application: Flask, dialog_count: int) -> tuple[list[int], int, int, int]:
    suffix = uuid4().hex
    now = datetime.now(UTC)
    with application.app_context():
        source = Role(code=f"auto_source_{suffix}", name="Auto source")
        target = Role(code=f"auto_target_{suffix}", name="Auto target")
        customer = Client(name="Auto-forward test", email=f"{suffix}@example.test")
        db.session.add_all([source, target, customer])
        db.session.flush()

        route = RoleRoute(
            source_role=source,
            target_role=target,
            is_default=True,
            auto_forward_after_minutes=1,
        )
        dialogs = [
            Dialog(
                client_id=customer.id,
                assigned_role=source,
                subject=f"Overdue dialog {index}",
                status=DialogStatus.OPEN,
                role_assigned_at=now - timedelta(minutes=10),
            )
            for index in range(dialog_count)
        ]
        db.session.add_all([route, *dialogs])
        db.session.commit()
        return [dialog.id for dialog in dialogs], source.id, target.id, customer.id


def _cleanup(
    application: Flask,
    dialog_ids: list[int],
    source_role_id: int,
    target_role_id: int,
    customer_id: int,
) -> None:
    with application.app_context():
        if dialog_ids:
            db.session.execute(delete(Message).where(Message.dialog_id.in_(dialog_ids)))
            db.session.execute(delete(Dialog).where(Dialog.id.in_(dialog_ids)))
        db.session.execute(
            delete(RoleRoute).where(
                RoleRoute.source_role_id == source_role_id,
                RoleRoute.target_role_id == target_role_id,
            )
        )
        db.session.execute(delete(Client).where(Client.id == customer_id))
        db.session.execute(delete(Role).where(Role.id.in_([source_role_id, target_role_id])))
        db.session.commit()


def test_parallel_workers_forward_each_dialog_once(postgres_app: Flask) -> None:
    """Two independent sessions must not forward the same dialog or duplicate events."""
    dialog_ids, source_id, target_id, customer_id = _create_scenario(postgres_app, 20)
    now = datetime.now(UTC)
    barrier = Barrier(2)

    def run_worker() -> int:
        with postgres_app.app_context():
            barrier.wait(timeout=15)
            return process_due_auto_forwards(now=now, limit=100)

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(run_worker) for _ in range(2)]
            processed = [future.result(timeout=30) for future in futures]

        assert sum(processed) == len(dialog_ids)

        with postgres_app.app_context():
            moved_count = db.session.scalar(
                db.select(func.count(Dialog.id)).where(
                    Dialog.id.in_(dialog_ids),
                    Dialog.assigned_role_id == target_id,
                )
            )
            event_count = db.session.scalar(
                db.select(func.count(Message.id)).where(
                    Message.dialog_id.in_(dialog_ids),
                    Message.author_type == AuthorType.SYSTEM,
                    Message.text.like("%автоматически передано%"),
                )
            )
            assert moved_count == len(dialog_ids)
            assert event_count == len(dialog_ids)
    finally:
        _cleanup(postgres_app, dialog_ids, source_id, target_id, customer_id)


def test_failed_commit_rolls_back_forward_and_event(postgres_app: Flask) -> None:
    """A failed transaction leaves the dialog eligible for the next worker cycle."""
    dialog_ids, source_id, target_id, customer_id = _create_scenario(postgres_app, 1)
    dialog_id = dialog_ids[0]

    try:
        with postgres_app.app_context():
            session = db.session()

            def fail_before_commit(active_session) -> None:
                raise RuntimeError("simulated failure before commit")

            event.listen(session, "before_commit", fail_before_commit, once=True)
            with pytest.raises(RuntimeError, match="simulated failure"):
                process_due_auto_forwards(now=datetime.now(UTC), limit=10)

            dialog = db.session.get(Dialog, dialog_id)
            assert dialog is not None
            assert dialog.assigned_role_id == source_id
            assert (
                db.session.scalar(
                    db.select(func.count(Message.id)).where(
                        Message.dialog_id == dialog_id,
                        Message.author_type == AuthorType.SYSTEM,
                        Message.text.like("%автоматически передано%"),
                    )
                )
                == 0
            )

            assert process_due_auto_forwards(now=datetime.now(UTC), limit=10) == 1
            db.session.refresh(dialog)
            assert dialog.assigned_role_id == target_id
    finally:
        _cleanup(postgres_app, dialog_ids, source_id, target_id, customer_id)
