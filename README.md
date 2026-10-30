# Support System

Базовый каркас системы технической поддержки на Flask. Это **модульный монолит**:
контексты развиваются в одном развёртываемом приложении, но не зависят от деталей
друг друга и могут быть выделены в сервисы позже.

## Стек

- Python 3.12, Flask, Pydantic Settings;
- SQLAlchemy 2.x, Alembic и отдельная PostgreSQL БД;
- pytest/pytest-cov, Ruff, mypy, Bandit и pip-audit;
- Docker Compose и GitHub Actions.

Зависимости описаны в `pyproject.toml` по стандарту PEP 621. Для локальной работы
используется `pip`: `pip install -e ".[dev]"`. Это намеренно простой и переносимый
вариант; lock-файл можно добавить при выборе корпоративного зеркала пакетов.

## Слои и границы

Каждый контекст в `app/modules/` содержит:

- `domain` — сущности, value objects, доменные события и интерфейсы портов. Здесь
  запрещены импорты Flask, SQLAlchemy, Redis, Celery и SDK внешних каналов.
- `application` — сценарии использования, команды/запросы и оркестрация домена.
- `infrastructure` — реализации портов: SQLAlchemy-репозитории, клиенты основной
  корпоративной БД, Telegram/VK/API-адаптеры.

`app/api` — единственный HTTP transport. Он вызывает application-слой, а
`app/infrastructure` содержит общие технические адаптеры. Никакой общий доступ к
ORM-моделям между контекстами не предполагается; взаимодействие строится через
application-порты и события. Корпоративная БД подключается будущим адаптером только
для чтения/синхронизации и не смешивается с БД поддержки.

Созданные контексты: authentication, clients, employees, dialogs, messages,
attachments, internal_notes, integrations и channels. Последние два заранее
выделяют границы для Web, Telegram, VK, внешнего API и виджета.

## Запуск

```bash
copy .env.example .env
docker compose up --build
```

Проверка живости: `GET http://localhost:8000/api/v1/health/live`.
Проверка готовности БД: `GET http://localhost:8000/api/v1/health/ready`.

После первого запуска примените миграции (`flask db upgrade`) и выполните
`flask bootstrap`. Команда создаёт системные роли и первоначальную учетную
запись администратора; временный пароль вводится интерактивно и не хранится
в `.env`. При первом входе система потребует его сменить.

## Режимы конфигурации

Переменные конфигурации имеют префикс `SUPPORT_`; `.env` исключён из Git, а
`.env.example` содержит только локальные, не секретные значения. Доступны режимы
`development`, `testing` и `production`. В production Flask debug запрещён
валидацией настроек. Тесты передают отдельный SQLite URL в памяти, а Docker Compose
использует именованный volume `tech_support_postgres_data`, который не связан с
какой-либо корпоративной или production БД.

## Разработка и миграции

```bash
pip install -e ".[dev]"
alembic revision --autogenerate -m "describe change"
alembic upgrade head
ruff check app tests
mypy app
bandit -c pyproject.toml -r app
pip-audit
pytest
```

Alembic смотрит исключительно на SQLAlchemy metadata инфраструктурного слоя. До
появления первых persistence-моделей миграций нет — это ожидаемое состояние каркаса.
При `docker compose up` отдельный одноразовый сервис `migrate` запускает `alembic
upgrade head` только после healthcheck PostgreSQL; Flask стартует лишь после его
успешного завершения. CI в `.github/workflows/ci.yml` запускает проверки кода, а
`.github/workflows/docker.yml` проверяет сборку image на push и pull request.
