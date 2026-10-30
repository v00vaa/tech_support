"""Database models for the support prototype."""

from app.models.attachment import Attachment
from app.models.client import Client
from app.models.dialog import Dialog, DialogStatus
from app.models.employee import Employee
from app.models.message import AuthorType, Message
from app.models.role import Permission, Role

__all__ = [
    "Attachment", "AuthorType", "Client", "Dialog", "DialogStatus",
    "Employee", "Message", "Permission", "Role",
]
