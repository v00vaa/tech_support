"""Tests for the persisted Web channel availability setting."""

from app.extensions import db
from app.models.general_settings import GeneralSettings


def test_web_channel_is_enabled_by_default_and_can_be_paused(app) -> None:
    with app.app_context():
        db.create_all()
        settings = GeneralSettings(id=1)
        db.session.add(settings)
        db.session.commit()

        assert settings.web_channel_enabled is True

        settings.web_channel_enabled = False
        db.session.commit()
        db.session.expire_all()

        stored = db.session.get(GeneralSettings, 1)
        assert stored is not None
        assert stored.web_channel_enabled is False
