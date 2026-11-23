# JSON API v1

Base path: `/api/v1`.

The API currently uses the same Flask-Login session as the browser interface. It is an employee API, not a public client API. Requests that modify data must include a valid CSRF token (for example, the `X-CSRFToken` header when using JSON). The liveness and readiness endpoints are public.

All errors use one JSON envelope:

```json
{
  "error": {
    "code": "Not Found",
    "message": "Обращение не найдено."
  }
}
```

## Endpoints

| Method | Path | Permission | Description |
| --- | --- | --- | --- |
| GET | `/health/live` | Public | Process liveness |
| GET | `/health/ready` | Public | Database readiness |
| GET | `/clients` | `clients.view` | List clients in the employee's visibility scope |
| POST | `/clients` | `clients.create` | Create a client |
| GET | `/employees` | `employees.view` | List employees in the employee's visibility scope |
| POST | `/employees` | `employees.create` | Create an employee |
| GET | `/dialogs` | `dialogs.view` | List accessible dialogs |
| GET | `/dialogs/{id}` | `dialogs.view` | Read one accessible dialog |
| GET | `/dialogs/{id}/messages` | `dialogs.view` | Read visible messages |
| POST | `/dialogs/{id}/messages` | `dialogs.reply` or `dialogs.add_internal_note` | Add a public message or internal note |

Creating dialogs through the employee API is deliberately disabled. A client creates a request from the client portal.

## Object-level access

- An active administrator can access all dialogs, clients, and employees.
- Other employees can access dialogs assigned to them, or unclaimed `OPEN` / `WAITING_EMPLOYEE` dialogs in their active `MAIN` roles. Special roles, already claimed queue items, and closed/resolved queue items do not grant queue access.
- A dialog outside this scope returns `404`, the same response as a missing dialog, to avoid exposing object identifiers.
- The client list is limited to clients who have at least one dialog visible to the employee.
- The employee list is limited to the employee's active-role colleagues; an employee without active roles sees only their own record.
- Client accounts cannot use employee API endpoints. Health checks remain public.

## Message visibility

- Soft-deleted messages are omitted.
- Internal notes are returned only to employees with `dialogs.add_internal_note`.
- Creating a public message requires `dialogs.reply`.
- Creating an internal note requires `dialogs.add_internal_note`.
- The API currently does not expose attachment upload or download endpoints.

## Input validation

- Mutating endpoints require a JSON object; arrays, scalar values, and null are rejected.
- Required text fields must be non-empty strings and are length-limited.
- Email addresses are validated and normalized before persistence.
- Duplicate client or employee email addresses return `409 Conflict`.
- Boolean fields must be JSON booleans; strings such as `"false"` are rejected.
- Employee passwords must contain 12–128 characters.
- Message text is limited to 10,000 characters.

## Current limitations

- Collection endpoints return arrays and do not yet provide pagination, sorting, or general-purpose filtering.
- The API uses browser session authentication; a separate machine-to-machine token scheme has not been implemented.
- Request/response validation is implemented in the route layer with typed helper functions. A dedicated schema package and generated OpenAPI specification remain future work.
