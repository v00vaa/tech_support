"""Tests for global settings defaults and persistence."""

from app.extensions import db
from app.models import GeneralSettings


def test_closed_dialog_retention_defaults_to_never(app):
    with app.app_context():
        db.create_all()
        settings = GeneralSettings(id=1)
        db.session.add(settings)
        db.session.commit()

        stored = db.session.get(GeneralSettings, 1)
        assert stored is not None
        assert stored.closed_dialog_retention_days is None
        assert stored.ai_assistant_enabled is False
        assert stored.ai_assistant_context == ""

        db.session.remove()
        db.drop_all()
