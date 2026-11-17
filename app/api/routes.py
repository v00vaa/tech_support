"""Versioned JSON API with employee RBAC and object-level access checks."""

from email_validator import EmailNotValidError, validate_email
from flask import Blueprint, abort, jsonify, request
from flask.typing import ResponseReturnValue
from flask_login import current_user
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql.elements import ColumnElement

from app.extensions import db
from app.models import AuthorType, Client, Dialog, Employee, Message
from app.models.role import employee_roles
from app.services import client_service, employee_service, message_service
from app.services.access_control_service import has_permission, is_active_administrator

api_bp = Blueprint("api", __name__, url_prefix="/api/v1")


def _employee() -> Employee:
    """Return the authenticated employee principal."""
    user = current_user._get_current_object()
    if not isinstance(user, Employee) or not user.is_active:
        abort(403, description="Служебный API доступен только активным сотрудникам.")
    return user


def _dialog_access_clause(employee: Employee) -> ColumnElement[bool] | None:
    """Build the object-level scope: own dialogs and queues of active roles."""
    if is_active_administrator(employee):
        return None
    role_ids = [role.id for role in employee.roles if role.is_active]
    clauses = [Dialog.responsible_employee_id == employee.id]
    if role_ids:
        clauses.append(Dialog.assigned_role_id.in_(role_ids))
    return or_(*clauses)


def _accessible_dialog(dialog_id: int) -> Dialog:
    """Load a dialog only if it belongs to the employee's permitted scope."""
    employee = _employee()
    statement = select(Dialog).where(Dialog.id == dialog_id)
    access_clause = _dialog_access_clause(employee)
    if access_clause is not None:
        statement = statement.where(access_clause)
    dialog = db.session.scalar(statement)
    if dialog is None:
        # Use 404 for both missing and inaccessible objects to prevent ID probing.
        abort(404, description="Обращение не найдено.")
    return dialog


def _json_object() -> dict[str, object]:
    """Require a JSON object instead of silently accepting arrays/scalars/null."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, description="Тело запроса должно быть JSON-объектом.")
    return data


def _required_text(data: dict[str, object], field: str, max_length: int) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        abort(400, description=f"Поле {field} обязательно и должно быть строкой.")
    value = value.strip()
    if len(value) > max_length:
        abort(400, description=f"Поле {field} превышает допустимую длину.")
    return value


def _validated_email(data: dict[str, object]) -> str:
    """Validate and normalize an email address before persisting it."""
    value = _required_text(data, "email", 255)
    try:
        return validate_email(value, check_deliverability=False).normalized
    except EmailNotValidError:
        abort(400, description="Поле email должно содержать корректный адрес.")


def _optional_text(
    data: dict[str, object], field: str, max_length: int
) -> str | None:
    value = data.get(field)
    if value is None:
        return None
    if not isinstance(value, str):
        abort(400, description=f"Поле {field} должно быть строкой.")
    value = value.strip()
    if len(value) > max_length:
        abort(400, description=f"Поле {field} превышает допустимую длину.")
    return value or None


def _client_data(client: Client) -> dict[str, object]:
    return {"id": client.id, "name": client.name, "email": client.email, "phone": client.phone}


def _employee_data(employee: Employee) -> dict[str, object]:
    return {
        "id": employee.id,
        "name": employee.name,
        "email": employee.email,
        "position": employee.position,
        "is_active": employee.is_active,
    }


def _dialog_data(dialog: Dialog) -> dict[str, object]:
    return {
        "id": dialog.id,
        "client_id": dialog.client_id,
        "responsible_employee_id": dialog.responsible_employee_id,
        "assigned_role_id": dialog.assigned_role_id,
        "subject": dialog.subject,
        "status": dialog.status.value,
        "channel": dialog.channel,
    }


def _message_data(message: Message) -> dict[str, object]:
    return {
        "id": message.id,
        "dialog_id": message.dialog_id,
        "author_type": message.author_type.value,
        "author_id": message.author_id,
        "text": message.text,
        "deleted_at": message.deleted_at.isoformat() if message.deleted_at else None,
        "is_internal": message.is_internal,
    }


@api_bp.before_request
def enforce_api_permissions() -> None:
    """Require an employee principal and the permission for the requested operation."""
    if request.endpoint in {"api.liveness", "api.readiness"}:
        return
    if not current_user.is_authenticated:
        abort(401)
    employee = _employee()
    permission_by_endpoint = {
        "api.clients": "clients.view"
        if request.method in {"GET", "HEAD"}
        else "clients.create",
        "api.employees": "employees.view"
        if request.method in {"GET", "HEAD"}
        else "employees.create",
        "api.dialogs": "dialogs.view",
        "api.dialog_detail": "dialogs.view",
        "api.messages": "dialogs.view",
    }
    required = permission_by_endpoint.get(request.endpoint or "")
    if required is None or not has_permission(employee, required):
        abort(403)


@api_bp.get("/health/live")
def liveness() -> ResponseReturnValue:
    return jsonify(status="ok"), 200


@api_bp.get("/health/ready")
def readiness() -> ResponseReturnValue:
    try:
        db.session.execute(db.text("SELECT 1"))
    except Exception:
        return jsonify(status="not_ready"), 503
    return jsonify(status="ok"), 200


@api_bp.route("/clients", methods=["GET", "POST"])
def clients() -> ResponseReturnValue:
    employee = _employee()
    if request.method in {"GET", "HEAD"}:
        statement = select(Client).order_by(Client.id)
        if not is_active_administrator(employee):
            access_clause = _dialog_access_clause(employee)
            statement = statement.where(
                Client.id.in_(
                    select(Dialog.client_id)
                    .where(access_clause)
                    .distinct()
                )
            )
        return jsonify([_client_data(item) for item in db.session.scalars(statement)]), 200

    data = _json_object()
    name = _required_text(data, "name", 120)
    email = _validated_email(data)
    phone = _optional_text(data, "phone", 40)
    try:
        client = client_service.create_client(name, email, phone)
    except IntegrityError:
        db.session.rollback()
        abort(409, description="Клиент с таким email уже существует.")
    return jsonify(_client_data(client)), 201


@api_bp.route("/employees", methods=["GET", "POST"])
def employees() -> ResponseReturnValue:
    employee = _employee()
    if request.method in {"GET", "HEAD"}:
        statement = select(Employee).order_by(Employee.id)
        if not is_active_administrator(employee):
            role_ids = [role.id for role in employee.roles if role.is_active]
            if role_ids:
                statement = statement.where(
                    Employee.id.in_(
                        select(employee_roles.c.employee_id).where(
                            employee_roles.c.role_id.in_(role_ids)
                        )
                    )
                )
            else:
                statement = statement.where(Employee.id == employee.id)
        return jsonify([_employee_data(item) for item in db.session.scalars(statement)]), 200

    data = _json_object()
    name = _required_text(data, "name", 120)
    email = _validated_email(data)
    password_value = data.get("password")
    if not isinstance(password_value, str) or len(password_value) < 12:
        abort(400, description="Пароль должен содержать не менее 12 символов.")
    password = password_value
    position = _optional_text(data, "position", 120) or "Специалист поддержки"
    is_active = data.get("is_active", True)
    if not isinstance(is_active, bool):
        abort(400, description="Поле is_active должно быть логическим значением.")
    try:
        created_employee = employee_service.create_employee(
            name, email, position, password, is_active
        )
    except IntegrityError:
        db.session.rollback()
        abort(409, description="Сотрудник с таким email уже существует.")
    return jsonify(_employee_data(created_employee)), 201


@api_bp.route("/dialogs", methods=["GET", "POST"])
def dialogs() -> ResponseReturnValue:
    if request.method == "POST":
        abort(403, description="Создание обращений сотрудниками через API отключено.")
    employee = _employee()
    statement = select(Dialog).order_by(Dialog.id)
    access_clause = _dialog_access_clause(employee)
    if access_clause is not None:
        statement = statement.where(access_clause)
    return jsonify([_dialog_data(item) for item in db.session.scalars(statement)]), 200


@api_bp.get("/dialogs/<int:dialog_id>")
def dialog_detail(dialog_id: int) -> ResponseReturnValue:
    dialog = _accessible_dialog(dialog_id)
    return jsonify(_dialog_data(dialog)), 200


@api_bp.route("/dialogs/<int:dialog_id>/messages", methods=["GET", "POST"])
def messages(dialog_id: int) -> ResponseReturnValue:
    dialog = _accessible_dialog(dialog_id)
    employee = _employee()
    if request.method in {"GET", "HEAD"}:
        statement = (
            select(Message)
            .where(Message.dialog_id == dialog.id, Message.deleted_at.is_(None))
            .order_by(Message.created_at, Message.id)
        )
        if not has_permission(employee, "dialogs.add_internal_note"):
            statement = statement.where(Message.is_internal.is_(False))
        visible_messages = db.session.scalars(statement)
        return jsonify([_message_data(item) for item in visible_messages]), 200

    data = _json_object()
    message_text = _required_text(data, "text", 10000)
    is_internal = data.get("is_internal", False)
    if not isinstance(is_internal, bool):
        abort(400, description="Поле is_internal должно быть логическим значением.")
    required = "dialogs.add_internal_note" if is_internal else "dialogs.reply"
    if not has_permission(employee, required):
        abort(403)
    message = message_service.create_message(
        dialog.id,
        AuthorType.EMPLOYEE,
        employee.id,
        message_text,
        is_internal=is_internal,
    )
    return jsonify(_message_data(message)), 201
