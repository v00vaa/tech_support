"""Tests for customer password-reset flow and enumeration resistance."""

from app.extensions import db, limiter
from app.models import Client


def test_reset_request_has_generic_response_for_unknown_email(client, customer_records):
    response = client.post(
        "/client/password-reset",
        data={"email": "missing@example.com"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Если активный аккаунт с таким email существует".encode() in response.data


def test_reset_request_sends_link_for_existing_account(app, client, customer_records):
    sent: list[tuple[str, str, str]] = []
    app.config["PASSWORD_RESET_EMAIL_SENDER"] = lambda to, subject, body: sent.append(
        (to, subject, body)
    )
    response = client.post(
        "/client/password-reset",
        data={"email": "one@example.com"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert len(sent) == 1
    assert sent[0][0] == "one@example.com"
    assert "/client/password-reset/" in sent[0][2]


def test_password_reset_token_changes_password_once(app, client, customer_records):
    from app.services.password_reset_service import generate_password_reset_token

    customer_id = customer_records
    with app.app_context():
        customer = db.session.get(Client, customer_id)
        assert customer is not None
        token = generate_password_reset_token(customer)

    response = client.post(
        f"/client/password-reset/{token}",
        data={
            "password": "new-customer-password",
            "confirm_password": "new-customer-password",
        },
    )
    assert response.status_code == 302
    with app.app_context():
        customer = db.session.get(Client, customer_id)
        assert customer is not None
        assert customer.check_password("new-customer-password")
        assert not customer.check_password("correct-horse-battery")

    # The same token must no longer work after the password hash changes.
    reused = client.get(f"/client/password-reset/{token}")
    assert reused.status_code == 400


def test_reset_request_does_not_send_for_client_without_email(app, client, customer_records):
    sent: list[tuple[str, str, str]] = []
    app.config["PASSWORD_RESET_EMAIL_SENDER"] = lambda to, subject, body: sent.append(
        (to, subject, body)
    )
    with app.app_context():
        customer = db.session.scalar(db.select(Client).where(Client.login == "customer-one"))
        assert customer is not None
        customer.email = None
        db.session.commit()
    client.post("/client/password-reset", data={"email": "one@example.com"})
    assert sent == []


def test_client_login_is_rate_limited(app, client, customer_records):
    # The app fixture initializes Flask-Limiter with limiting disabled.
    # Re-initialize it after enabling the config so its request hooks are registered.
    app.config["RATELIMIT_ENABLED"] = True
    limiter.init_app(app)
    responses = [
        client.post(
            "/client/login",
            data={"login": "unknown-user", "password": "wrong-password"},
        )
        for _ in range(6)
    ]
    assert all(response.status_code == 200 for response in responses[:5])
    assert responses[5].status_code == 429
