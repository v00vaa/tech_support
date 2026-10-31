"""Central permission catalogue used by RBAC bootstrap and administration."""

from typing import TypedDict


class PermissionDefinition(TypedDict):
    code: str
    name: str
    description: str
    category: str


PERMISSION_DEFINITIONS: tuple[PermissionDefinition, ...] = (
    {"code": "clients.view", "name": "Просмотр клиентов", "description": "Просмотр карточек клиентов", "category": "clients"},
    {"code": "clients.create", "name": "Создание клиентов", "description": "Добавление клиентов", "category": "clients"},
    {"code": "clients.edit", "name": "Изменение клиентов", "description": "Изменение карточек клиентов", "category": "clients"},
    {"code": "clients.delete", "name": "Удаление клиентов", "description": "Удаление карточек клиентов", "category": "clients"},
    {"code": "employees.view", "name": "Просмотр сотрудников", "description": "Просмотр списка и карточек сотрудников", "category": "employees"},
    {"code": "employees.create", "name": "Создание сотрудников", "description": "Добавление сотрудников", "category": "employees"},
    {"code": "employees.edit", "name": "Изменение сотрудников", "description": "Изменение данных сотрудников", "category": "employees"},
    {"code": "employees.deactivate", "name": "Деактивация сотрудников", "description": "Отключение учетных записей сотрудников", "category": "employees"},
    {"code": "employees.assign_roles", "name": "Назначение ролей", "description": "Назначение сотрудникам доступных ролей", "category": "employees"},
    {"code": "roles.view", "name": "Просмотр ролей", "description": "Просмотр ролей и разрешений", "category": "roles"},
    {"code": "roles.create", "name": "Создание ролей", "description": "Создание пользовательских ролей", "category": "roles"},
    {"code": "roles.edit", "name": "Изменение ролей", "description": "Изменение пользовательских ролей", "category": "roles"},
    {"code": "roles.assign_permissions", "name": "Назначение разрешений", "description": "Изменение набора разрешений роли", "category": "roles"},
    {"code": "dialogs.view", "name": "Просмотр диалогов", "description": "Просмотр обращений поддержки", "category": "dialogs"},
    {"code": "dialogs.create", "name": "Создание диалогов", "description": "Создание обращений", "category": "dialogs"},
    {"code": "dialogs.manage", "name": "Управление диалогами", "description": "Изменение и удаление обращений", "category": "dialogs"},
    {"code": "dialogs.change_status", "name": "Изменение статуса", "description": "Изменение статуса обращения", "category": "dialogs"},
    {"code": "dialogs.reply", "name": "Ответ клиенту", "description": "Отправка публичных ответов", "category": "dialogs"},
    {"code": "dialogs.add_internal_note", "name": "Внутренние заметки", "description": "Добавление заметок, видимых только сотрудникам", "category": "dialogs"},
    {"code": "dialogs.transfer", "name": "Передача диалогов", "description": "Передача обращения другому сотруднику или этапу", "category": "dialogs"},
    {"code": "settings.view", "name": "Просмотр настроек", "description": "Просмотр системных настроек", "category": "settings"},
    {"code": "settings.edit", "name": "Изменение настроек", "description": "Изменение системных настроек", "category": "settings"},
)

SUPPORT_LEVEL_1_PERMISSIONS = frozenset(
    {
        "clients.view",
        "dialogs.view",
        "dialogs.reply",
        "dialogs.add_internal_note",
        "dialogs.change_status",
        "dialogs.transfer",
    }
)
