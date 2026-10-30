"""Client CRUD operations."""

from app.extensions import db
from app.models.client import Client


def create_client(name: str, email: str, phone: str | None) -> Client:
    client = Client(name=name, email=email, phone=phone or None)
    db.session.add(client)
    db.session.commit()
    return client


def update_client(client: Client, name: str, email: str, phone: str | None) -> Client:
    client.name, client.email, client.phone = name, email, phone or None
    db.session.commit()
    return client


def delete_client(client: Client) -> None:
    db.session.delete(client)
    db.session.commit()
