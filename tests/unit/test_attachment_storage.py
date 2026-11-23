"""Tests for private attachment storage cleanup."""

import os
from datetime import UTC, datetime, timedelta

from app.extensions import db
from app.models import (
    Attachment,
    AuthorType,
    Client,
    Dialog,
    DialogStatus,
    GeneralSettings,
)
from app.services import dialog_service, message_service
from app.services.attachment_storage_service import (
    cleanup_expired_closed_dialogs,
    remove_orphaned_attachment_files,
)


def test_orphan_cleanup_removes_only_old_unreferenced_files(app, tmp_path, monkeypatch) -> None:
    with app.app_context():
        db.create_all()
        monkeypatch.setattr(app, "instance_path", str(tmp_path))
        storage_dir = tmp_path / "uploads"
        storage_dir.mkdir()

        referenced = storage_dir / "referenced.pdf"
        orphaned = storage_dir / "orphaned.pdf"
        recent = storage_dir / "recent.pdf"
        referenced.write_bytes(b"referenced")
        orphaned.write_bytes(b"orphaned")
        recent.write_bytes(b"recent")

        customer = Client(name="Cleanup Client", email="cleanup-client@example.com")
        db.session.add(customer)
        db.session.commit()
        dialog = dialog_service.create_dialog(customer.id, None, "Cleanup", "Web")
        message = message_service.create_message(dialog.id, AuthorType.CLIENT, customer.id, "File")
        db.session.add(
            Attachment(
                message_id=message.id,
                filename=referenced.name,
                storage_key=referenced.name,
                content_type="application/pdf",
                size_bytes=10,
            )
        )
        db.session.commit()

        old_timestamp = (datetime.now(UTC) - timedelta(days=2)).timestamp()
        os.utime(orphaned, (old_timestamp, old_timestamp))

        removed = remove_orphaned_attachment_files(min_age_hours=24)

        assert removed == 1
        assert referenced.exists()
        assert not orphaned.exists()
        assert recent.exists()


def test_orphan_cleanup_rejects_negative_grace_period(app) -> None:
    with app.app_context():
        try:
            remove_orphaned_attachment_files(min_age_hours=-1)
        except ValueError as error:
            assert "must not be negative" in str(error)
        else:
            raise AssertionError("Negative grace period must be rejected")


def test_retention_cleanup_is_disabled_when_never_is_selected(app, tmp_path, monkeypatch) -> None:
    with app.app_context():
        db.create_all()
        monkeypatch.setattr(app, "instance_path", str(tmp_path))
        customer = Client(name="Retention Client", email="retention-never@example.com")
        db.session.add(customer)
        db.session.commit()
        dialog = dialog_service.create_dialog(customer.id, None, "Keep forever", "Web")
        dialog_service.change_status(dialog, DialogStatus.CLOSED)

        db.session.add(GeneralSettings(id=1, closed_dialog_retention_days=None))
        db.session.commit()

        assert cleanup_expired_closed_dialogs() == 0
        assert db.session.get(Dialog, dialog.id) is not None


def test_retention_cleanup_deletes_only_expired_closed_dialogs_and_files(
    app, tmp_path, monkeypatch
) -> None:
    with app.app_context():
        db.create_all()
        monkeypatch.setattr(app, "instance_path", str(tmp_path))
        storage_dir = tmp_path / "uploads"
        storage_dir.mkdir()
        old_file = storage_dir / "expired.pdf"
        old_file.write_bytes(b"%PDF-1.7")

        customer = Client(name="Retention Client", email="retention-days@example.com")
        db.session.add(customer)
        db.session.commit()
        expired = dialog_service.create_dialog(customer.id, None, "Expired", "Web")
        expired.status = DialogStatus.CLOSED
        expired.closed_at = datetime.now(UTC) - timedelta(days=45)
        active = dialog_service.create_dialog(customer.id, None, "Still open", "Web")
        recent = dialog_service.create_dialog(customer.id, None, "Recently closed", "Web")
        recent.status = DialogStatus.CLOSED
        recent.closed_at = datetime.now(UTC) - timedelta(days=10)
        message = message_service.create_message(
            expired.id, AuthorType.CLIENT, customer.id, "Old attachment"
        )
        db.session.add(
            Attachment(
                message_id=message.id,
                filename=old_file.name,
                storage_key=old_file.name,
                content_type="application/pdf",
                size_bytes=8,
            )
        )
        db.session.add(GeneralSettings(id=1, closed_dialog_retention_days=30))
        db.session.commit()

        assert cleanup_expired_closed_dialogs() == 1
        assert db.session.get(Dialog, expired.id) is None
        assert db.session.get(Dialog, active.id) is not None
        assert db.session.get(Dialog, recent.id) is not None
        assert not old_file.exists()
