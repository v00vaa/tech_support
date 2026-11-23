"""Customer data isolation tests for direct browser URLs and attachment downloads."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from flask import Flask
from flask.testing import FlaskClient

from app.extensions import db
from app.models import Attachment, AuthorType, Client, Dialog, DialogStatus, Message


@pytest.fixture
def isolated_customer_data(
    app: Flask,
    client: FlaskClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[dict[str, int]]:
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    monkeypatch.setattr(app, "instance_path", str(tmp_path))
    uploads_dir = tmp_path / "uploads"
    uploads_dir.mkdir()

    with app.app_context():
        db.create_all()
        first_customer = Client(
            name="First customer",
            login="first-customer",
            email="first-customer@example.com",
        )
        second_customer = Client(
            name="Second customer",
            login="second-customer",
            email="second-customer@example.com",
        )
        first_customer.set_password("First-customer-password-123!")
        second_customer.set_password("Second-customer-password-123!")
        db.session.add_all([first_customer, second_customer])
        db.session.flush()

        first_dialog = Dialog(
            client_id=first_customer.id,
            subject="First customer's private request",
            status=DialogStatus.OPEN,
            channel="Web",
        )
        second_dialog = Dialog(
            client_id=second_customer.id,
            subject="Second customer's private request",
            status=DialogStatus.OPEN,
            channel="Web",
        )
        db.session.add_all([first_dialog, second_dialog])
        db.session.flush()

        own_public_message = Message(
            dialog_id=first_dialog.id,
            author_type=AuthorType.CLIENT,
            author_id=first_customer.id,
            text="First customer's public message",
            is_internal=False,
        )
        own_internal_message = Message(
            dialog_id=first_dialog.id,
            author_type=AuthorType.EMPLOYEE,
            author_id=None,
            text="Internal employee-only note",
            is_internal=True,
        )
        foreign_message = Message(
            dialog_id=second_dialog.id,
            author_type=AuthorType.CLIENT,
            author_id=second_customer.id,
            text="Second customer's secret message",
            is_internal=False,
        )
        db.session.add_all([own_public_message, own_internal_message, foreign_message])
        db.session.flush()

        attachments = [
            Attachment(
                message_id=own_public_message.id,
                filename="own.txt",
                storage_key="own.txt",
                content_type="text/plain",
                size_bytes=11,
            ),
            Attachment(
                message_id=own_internal_message.id,
                filename="internal.txt",
                storage_key="internal.txt",
                content_type="text/plain",
                size_bytes=18,
            ),
            Attachment(
                message_id=foreign_message.id,
                filename="foreign.txt",
                storage_key="foreign.txt",
                content_type="text/plain",
                size_bytes=13,
            ),
        ]
        db.session.add_all(attachments)
        db.session.commit()

        (uploads_dir / "own.txt").write_text("own content", encoding="utf-8")
        (uploads_dir / "internal.txt").write_text("internal content", encoding="utf-8")
        (uploads_dir / "foreign.txt").write_text("foreign content", encoding="utf-8")

        ids = {
            "customer": first_customer.id,
            "own_dialog": first_dialog.id,
            "foreign_dialog": second_dialog.id,
            "own_public_message": own_public_message.id,
            "own_internal_message": own_internal_message.id,
            "foreign_message": foreign_message.id,
            "own_attachment": attachments[0].id,
            "internal_attachment": attachments[1].id,
            "foreign_attachment": attachments[2].id,
        }

    with client.session_transaction() as session:
        session["_user_id"] = f"client:{ids['customer']}"
        session["_fresh"] = True

    yield ids

    with app.app_context():
        db.session.remove()
        db.drop_all()


def test_customer_cannot_open_another_customers_dialog_or_messages(
    client: FlaskClient,
    isolated_customer_data: dict[str, int],
) -> None:
    ids = isolated_customer_data

    portal = client.get("/portal/")
    assert portal.status_code == 200
    portal_text = portal.get_data(as_text=True)
    assert "First customer's private request" in portal_text
    assert "Second customer's private request" not in portal_text

    own_dialog = client.get(f"/portal/dialogs/{ids['own_dialog']}")
    assert own_dialog.status_code == 200
    own_text = own_dialog.get_data(as_text=True)
    assert "First customer's public message" in own_text
    assert "Internal employee-only note" not in own_text
    assert "Second customer's secret message" not in own_text

    assert client.get(f"/portal/dialogs/{ids['foreign_dialog']}").status_code == 404
    assert (
        client.post(
            f"/portal/dialogs/{ids['foreign_dialog']}",
            data={"text": "Unauthorized reply", "submit": "Send"},
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/dialogs/{ids['foreign_dialog']}/messages",
            data={"text": "Unauthorized employee reply", "submit": "Send"},
        ).status_code
        == 403
    )


def test_customer_can_download_only_own_public_attachments(
    client: FlaskClient,
    isolated_customer_data: dict[str, int],
) -> None:
    ids = isolated_customer_data

    own_file = client.get(f"/messages/attachments/{ids['own_attachment']}")
    assert own_file.status_code == 200
    assert own_file.data == b"own content"

    foreign_file = client.get(f"/messages/attachments/{ids['foreign_attachment']}")
    assert foreign_file.status_code == 404

    internal_file = client.get(f"/messages/attachments/{ids['internal_attachment']}")
    assert internal_file.status_code == 404

    assert client.get(f"/messages/{ids['foreign_message']}/edit").status_code == 403
    assert client.post(f"/messages/{ids['foreign_message']}/delete").status_code == 403
