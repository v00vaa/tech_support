# Support Desk

Веб-система технической поддержки на Flask. Проект реализован как модульный монолит: веб-интерфейс, служебный JSON API, доменные сервисы и persistence-модели находятся в одном приложении и используют общую PostgreSQL БД.

## Технологии

- Python 3.12+, Flask 3, Flask-Login, Flask-WTF;
- SQLAlchemy 2, Flask-Migrate и Alembic;
- PostgreSQL 16, Redis для shared rate limiting в production;
- pytest, pytest-cov, Ruff, mypy, Bandit и pip-audit;
- Docker Compose и GitHub Actions.

## Структура проекта

```text
app/
  api/          # версионированный JSON API (/api/v1)
  core/         # конфигурация, обработчики ошибок, CLI-команды
  models/       # SQLAlchemy-модели и связи
  services/     # бизнес-операции, маршрутизация, доступ, вложения
  web/          # Flask blueprints, формы и HTTP-маршруты
  templates/    # Jinja2-шаблоны интерфейса
  static/       # статические ресурсы
migrations/     # Alembic-миграции
tests/
  unit/
  api/
  integration/
  e2e/
docs/           # API, интеграционные контракты и RBAC
wsgi.py         # WSGI entrypoint
```

Слои организованы по фактическим каталогам `app/models`, `app/services`, `app/web` и `app/api`; каталоги `app/modules` и `app/infrastructure` не используются.

## Возможности

- клиентский личный кабинет и создание обращений;
- очередь обращений по основной роли первого уровня;
- централизованный редактор маршрутов между ролями и правил автоматической передачи обращений;
- захват обращения сотрудником и маршрутизация по настроенным правилам;
- разграничение прав по ролям и объектной области доступа;
- приглашения сотрудников по одноразовым ссылкам с назначением основной роли и первичной установкой пароля;
- публичные сообщения, внутренние заметки и приватные вложения;
- soft-delete сообщений и физическое удаление вложений после удаления обращения;
- JSON API для сотрудников с RBAC и проверкой доступа к объектам;
- восстановление пароля клиента через подписанную ссылку и SMTP;
- отправка приглашений сотрудников через SMTP; приглашения действуют 72 часа, могут быть отозваны и принимаются только один раз;
- интеграционный адаптер регистрации из основной системы;
- worker для автоматической маршрутизации и ежедневного применения срока хранения закрытых обращений.

## Быстрый запуск через Docker Compose

Скопируйте пример конфигурации:

```powershell
Copy-Item .env.example .env
```

Запустите сервисы:

```powershell
docker compose up --build -d
```

Compose поднимает PostgreSQL, Redis, одноразовый сервис миграций, Flask/Gunicorn и отдельный worker. Приложение доступно по адресу http://localhost:5000. PostgreSQL использует именованный volume, вложения хранятся отдельно в приватном volume `support_uploads`.

Создайте первоначальные системные роли и администратора:

```powershell
docker compose exec app flask --app wsgi:app bootstrap
```

Команда запросит email и временный пароль администратора. При первом входе система потребует сменить пароль.

Проверки состояния:
- `GET /api/v1/health/live` — процесс приложения;
- `GET /api/v1/health/ready` — готовность подключения к БД.

Остановка:

```powershell
docker compose down
```

Для удаления также данных БД и загруженных файлов потребуется отдельное явное удаление volumes; обычный `docker compose down` сохраняет их.

## Локальная разработка

Требуется Python 3.12 или новее и доступная PostgreSQL. Установите проект с инструментами разработки:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
Copy-Item .env.example .env
```

Настройте `SUPPORT_DATABASE_URL` в `.env`, затем примените миграции и запустите приложение:

```powershell
alembic upgrade head
flask --app wsgi:app bootstrap
flask --app wsgi:app run
```

Все переменные окружения имеют префикс `SUPPORT_`. Основные режимы: `development`, `testing`, `production`. Production-конфигурация требует HTTPS, уникальный секрет, Redis для rate limiting, HTTP-интеграцию регистрации и настроенный SMTP.

## Worker и срок хранения

Отдельный Compose-сервис `worker` обрабатывает автоматическую передачу обращений. Он также ежедневно запускает очистку закрытых обращений согласно общей настройке **«Срок хранения закрытых обращений»**. Значение **«Никогда»** установлено по умолчанию и отключает автоматическое удаление. Доступные сроки: 30, 90, 180 и 365 дней.

Ручные команды:

```powershell
flask --app wsgi:app cleanup-expired-dialogs --limit 100
flask --app wsgi:app cleanup-orphaned-attachments --min-age-hours 24
```

Первая команда применяет настроенный срок хранения. Вторая удаляет только файлы, на которые не ссылается БД и которые старше защитного интервала.

## Резервное копирование и восстановление

Сценарии PowerShell находятся в `scripts/`. Перед резервным копированием скрипт останавливает веб-приложение и worker, чтобы PostgreSQL dump и каталог вложений соответствовали одному состоянию. После операции восстанавливается исходное состояние app/worker.

Создание копии (PostgreSQL в формате custom, приватные вложения и SHA-256 manifest):

```powershell
.\scripts\backup.ps1
```

Восстановление из выбранного каталога (перед изменением данных проверяются контрольные суммы):

```powershell
.\scripts\restore.ps1 -BackupPath .\backups\20261123-120000
```

Восстановление заменяет содержимое БД и каталога вложений. Выполняйте его только после выбора правильной копии и убедитесь, что другие процессы/администраторы не записывают данные в БД. Скрипты не запускают Docker Desktop и не включают сервисы, если они не были запущены до операции; сервис `db` должен быть запущен, а контейнер `app` создан. Резервные копии в каталоге `backups/` исключены из Git.

## Тесты и проверки качества

```powershell
ruff check app tests
ruff format --check app tests
mypy app
bandit -c pyproject.toml -r app
pip-audit
pytest
```

Для PostgreSQL integration-тестов задайте отдельную тестовую БД через `SUPPORT_TEST_POSTGRES_URL`. Не используйте production БД для тестов.

GitHub Actions запускает Ruff, Mypy, security checks и тесты/миграции параллельно. Сборка Docker image в CI зависит от успешного завершения всех четырёх проверок.

## Документация

- [JSON API v1](docs/api.md)
- [Интеграция регистрации с основной системой](docs/registration-integration.md)
- [Аутентификация клиентов](docs/client-authentication.md)
- [Права и роли](docs/role-permissions.md)
- [Маршрутизация обращений](docs/role-routing.md)

