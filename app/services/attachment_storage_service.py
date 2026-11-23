"""Private attachment storage cleanup helpers."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from flask import current_app

from app.extensions import db
from app.models import Attachment, Dialog, DialogStatus, GeneralSettings


def _storage_directory() -> Path:
    return Path(current_app.instance_path) / "uploads"


def remove_attachment_files(storage_keys: list[str]) -> int:
    """Remove files only after their metadata transaction has committed."""
    storage_dir = _storage_directory()
    removed = 0
    for storage_key in storage_keys:
        if not storage_key or Path(storage_key).name != storage_key:
            current_app.logger.warning("Skipped unsafe attachment storage key: %r", storage_key)
            continue
        path = storage_dir / storage_key
        try:
            path.unlink(missing_ok=True)
            removed += 1
        except OSError:
            current_app.logger.exception("Could not remove attachment file %s", storage_key)
    return removed


def remove_orphaned_attachment_files(min_age_hours: int = 24) -> int:
    """Delete unreferenced regular files older than the grace period."""
    if min_age_hours < 0:
        raise ValueError("min_age_hours must not be negative")

    storage_dir = _storage_directory()
    if not storage_dir.exists():
        return 0

    referenced = set(
        db.session.scalars(db.select(Attachment.storage_key).where(Attachment.storage_key != ""))
    )
    cutoff = datetime.now(UTC).timestamp() - timedelta(hours=min_age_hours).total_seconds()
    removed = 0

    for path in storage_dir.iterdir():
        if path.name in referenced or path.is_symlink() or not path.is_file():
            continue
        try:
            if path.stat().st_mtime >= cutoff:
                continue
            path.unlink()
            removed += 1
        except OSError:
            current_app.logger.exception("Could not remove orphaned attachment file %s", path.name)
    return removed

def cleanup_expired_closed_dialogs(limit: int = 100) -> int:
    """Delete closed dialogs past the configured retention period and their files."""
    if limit < 1:
        raise ValueError("limit must be positive")

    settings = db.session.get(GeneralSettings, 1)
    if settings is None or settings.closed_dialog_retention_days is None:
        return 0

    cutoff = datetime.now(UTC) - timedelta(days=settings.closed_dialog_retention_days)
    expired_ids = list(
        db.session.scalars(
            db.select(Dialog.id)
            .where(
                Dialog.status == DialogStatus.CLOSED,
                Dialog.closed_at.is_not(None),
                Dialog.closed_at <= cutoff,
            )
            .order_by(Dialog.closed_at, Dialog.id)
            .limit(limit)
        )
    )

    removed = 0
    for dialog_id in expired_ids:
        dialog = db.session.scalar(
            db.select(Dialog)
            .where(
                Dialog.id == dialog_id,
                Dialog.status == DialogStatus.CLOSED,
                Dialog.closed_at.is_not(None),
                Dialog.closed_at <= cutoff,
            )
            .with_for_update(skip_locked=True)
        )
        if dialog is None:
            continue
        try:
            from app.services.dialog_service import delete_dialog

            delete_dialog(dialog)
            removed += 1
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Could not delete expired closed dialog %s", dialog_id)
    return removed
