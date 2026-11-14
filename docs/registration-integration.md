# Интеграция регистрации с основной системой

## Поток регистрации

1. Основная система создаёт криптографически случайный одноразовый handoff-токен (рекомендуется не менее 256 бит энтропии), сохраняет его хеш, срок действия, назначение и целевой Support Desk instance.
2. Пользователь открывает `https://<support-host>/register?token=<handoff-token>`.
3. Support Desk выполняет серверный HTTPS GET к основной системе. Браузер пользователя не обращается к API основной системы напрямую.
4. После подтверждения данных и создания локального аккаунта Support Desk отправляет отдельный POST для погашения handoff-токена.
5. Повторный POST с тем же Idempotency-Key должен возвращать тот же успешный результат, а не создавать побочный эффект повторно.

GET получения профиля не должен погашать токен: браузеры, прокси и клиенты могут повторять GET-запросы.

## Контракт основной системы

### Получение профиля

`GET /api/v1/support/registration-profile`

Заголовки:

- `Authorization: Bearer <support-service-credential>` — аутентификация экземпляра Support Desk.
- `X-Registration-Token: <handoff-token>` — временное разрешение получить профиль конкретного пользователя.
- `Accept: application/json`.

Успешный ответ HTTP 200:

```json
{
  "external_id": "customer-123",
  "name": "Имя клиента",
  "email": "client@example.com",
  "phone": null
}
```

`external_id` обязателен и стабилен в пределах основной системы. Остальные поля могут быть `null`. Возвращать пароль, платёжные сведения и не относящиеся к регистрации данные нельзя.

Ошибки:

- `401/403` — неверная/отозванная авторизация Support Desk;
- `404/410` — неизвестный, просроченный, отозванный или погашенный handoff-токен;
- `429` — превышен лимит запросов;
- `5xx` — временная ошибка основной системы.

### Погашение токена

`POST /api/v1/support/registration-token/redeem`

Те же `Authorization` и `X-Registration-Token`, дополнительно:

- `Content-Type: application/json`;
- `Idempotency-Key: support-client-<external_id>`.

Тело запроса — пустой JSON-объект `{}`. Успешный ответ HTTP 200/204. Основная система должна атомарно пометить токен использованным и сохранить результат операции по ключу идемпотентности. Повтор с тем же ключом должен быть безопасным.

## Конфигурация Support Desk

Все переменные используют префикс `SUPPORT_`:

| Переменная | Назначение |
| --- | --- |
| `REGISTRATION_PROVIDER` | `mock` для локальной разработки или `http` для реальной интеграции |
| `REGISTRATION_API_BASE_URL` | HTTPS base URL основной системы |
| `REGISTRATION_PROFILE_PATH` | Endpoint получения профиля |
| `REGISTRATION_REDEEM_PATH` | Endpoint погашения токена |
| `REGISTRATION_SERVICE_TOKEN` | Секрет сервисной авторизации Support Desk |
| `REGISTRATION_TIMEOUT_SECONDS` | Таймаут HTTP-запроса, по умолчанию 5 секунд |

Пример для локального `.env`:

```dotenv
SUPPORT_REGISTRATION_PROVIDER=mock
SUPPORT_REGISTRATION_TIMEOUT_SECONDS=5
```

Пример настройки HTTP-интеграции:

```dotenv
SUPPORT_REGISTRATION_PROVIDER=http
SUPPORT_REGISTRATION_API_BASE_URL=https://main.example.com
SUPPORT_REGISTRATION_PROFILE_PATH=/api/v1/support/registration-profile
SUPPORT_REGISTRATION_REDEEM_PATH=/api/v1/support/registration-token/redeem
SUPPORT_REGISTRATION_SERVICE_TOKEN=<secret-from-secret-manager>
SUPPORT_REGISTRATION_TIMEOUT_SECONDS=5
```

В production приложение запрещает режим `mock` и требует URL API и сервисный секрет. Секрет нельзя хранить в репозитории или передавать в URL.

## Обязательные меры защиты

- Только HTTPS; проверка сертификата TLS не отключается.
- Handoff-токен — случайный, короткоживущий (например, 5–10 минут), одноразовый, ограниченный назначением и конкретным экземпляром Support Desk.
- В основной системе хранить хеш handoff-токена, а не его открытое значение.
- Service credential и handoff-токен проверяются независимо.
- Ограничить частоту запросов получения профиля и погашения.
- Не включать query string регистрации, Authorization и X-Registration-Token в access/application logs, traces и error reports.
- Для страницы регистрации выставлять `Cache-Control: no-store` и `Referrer-Policy: no-referrer`; не загружать сторонние ресурсы до очистки URL от токена.
- Не помещать сервисный секрет в браузер, HTML, JavaScript или URL.
- Сопоставлять `external_id` с локальным клиентом и запрещать повторное создание профиля.

## Границы текущей реализации

В репозитории реализованы HTTP-адаптер и mock-адаптер. Mock нужен только для локальной демонстрации; он не является хранилищем токенов и не заменяет endpoint основной системы. Для подключения реальной системы её разработчикам необходимо реализовать контракт выше. Вход клиентов в отдельный кабинет остаётся отдельной задачей: текущий Flask-Login loader проекта аутентифицирует сотрудников.
