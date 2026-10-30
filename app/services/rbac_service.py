"""Idempotent creation of the built-in RBAC catalogue."""

from app.core.permissions import PERMISSION_DEFINITIONS, SUPPORT_LEVEL_1_PERMISSIONS
from app.extensions import db
from app.models.role import Permission, Role


def ensure_rbac_catalogue() -> tuple[Role, Role]:
    """Create or refresh built-in roles and permission definitions."""
    permissions_by_code: dict[str, Permission] = {}
    for definition in PERMISSION_DEFINITIONS:
        permission = db.session.scalar(
            db.select(Permission).where(Permission.code == definition["code"])
        )
        if permission is None:
            permission = Permission(**definition)
            db.session.add(permission)
        else:
            permission.name = definition["name"]
            permission.description = definition["description"]
            permission.category = definition["category"]
        permissions_by_code[permission.code] = permission

    administrator = db.session.scalar(
        db.select(Role).where(Role.code == "administrator")
    )
    if administrator is None:
        administrator = Role(
            code="administrator",
            name="Администратор",
            description="Полный доступ ко всем функциям системы",
            is_system=True,
        )
        db.session.add(administrator)

    support = db.session.scalar(
        db.select(Role).where(Role.code == "support_level_1")
    )
    if support is None:
        support = Role(
            code="support_level_1",
            name="Поддержка — уровень 1",
            description="Первичная обработка обращений клиентов",
            is_system=True,
        )
        db.session.add(support)

    db.session.flush()
    administrator.permissions = list(permissions_by_code.values())
    support.permissions = [
        permissions_by_code[code] for code in SUPPORT_LEVEL_1_PERMISSIONS
    ]
    db.session.commit()
    return administrator, support
