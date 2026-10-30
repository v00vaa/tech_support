"""Central permission catalogue used by RBAC bootstrap and administration."""

PERMISSION_DEFINITIONS: tuple[dict[str, str], ...] = (
    {"code": "clients.view", "name": "Просмотр клиентов", "description": "Просмотр карточек клиентов", "category": "clients"},
    {"code": "employees.view", "name": "Просмотр сотрудников", "description": "Просмотр списка и карточек сотрудников", "category": "employees"},
    {"code": "employees.create", "name": "Создание сотрудников", "description": "Добавление сотрудников", "category": "employees"},
    {"code": "employees.edit", "name": "Изменение сотрудников", "description": "Изменение данных сотрудников", "category": "employees"},
    {"code": "employees.deactivate", "name": "Деактивация сотрудников", "description": "Отключение учетных записей сотрудников", "category": "employees"},
    {"code": "roles.view", "name": "Просмотр ролей", "description": "Просмотр ролей и разрешений", "category": "roles"},
    {"code": "roles.create", "name": "Создание ролей", "description": "Создание пользовательских ролей", "category": "roles"},
    {"code": "roles.edit", "name": "Изменение ролей", "description": "Изменение пользовательских ролей", "category": "roles"},
    {"code": "roles.assign_permissions", "name": "Назначение разрешений", "description": "Изменение набора разрешений роли", "category": "roles"},
    {"code": "dialogs.view", "name": "Просмотр диалогов", "description": "Просмотр обращений поддержки", "category": "dialogs"},
    {"code": "dialogs.reply", "name": "Ответ клиенту", "description": "Отправка публичных ответов", "category": "dialogs"},
    {"code": "dialogs.add_internal_note", "name": "Внутренние заметки", "description": "Добавление заметок, видимых только сотрудникам", "category": "dialogs"},
    {"code": "dialogs.transfer", "name": "Передача диалогов", "description": "Передача обращения другому сотруднику или этапу", "category": "dialogs"},
    {"code": "settings.view", "name": "Просмотр настроек", "description": "Просмотр системных настроек", "category": "settings"},
    {"code": "settings.edit", "name": "Изменение настроек", "description": "Изменение системных настроек", "category": "settings"},
)

SUPPORT_LEVEL_1_PERMISSIONS = frozenset(
    {"clients.view", "dialogs.view", "dialogs.reply", "dialogs.add_internal_note", "dialogs.transfer"}
)
