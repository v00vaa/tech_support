"""Small JSON API sharing the same services as the HTML interface."""

from flask import Blueprint, ResponseReturnValue, abort, jsonify, request
from flask_login import current_user
from sqlalchemy import select

from app.extensions import db
from app.models import AuthorType, Client, Dialog, Employee, Message
from app.services import client_service, dialog_service, employee_service, message_service
from app.services.access_control_service import has_permission

api_bp = Blueprint("api", __name__, url_prefix="/api/v1")

@api_bp.before_request
def enforce_api_permissions() -> None:
    """Apply RBAC to JSON endpoints while leaving health checks public."""
    if request.endpoint in {"api.liveness", "api.readiness"}:
        return
    if not current_user.is_authenticated:
        abort(401)
    permission_by_endpoint = {
        "api.clients": "clients.view" if request.method == "GET" else "clients.create",
        "api.employees": "employees.view" if request.method == "GET" else "employees.create",
        "api.dialogs": "dialogs.view" if request.method == "GET" else "dialogs.create",
        "api.dialog_detail": "dialogs.view",
        "api.messages": "dialogs.view" if request.method == "GET" else "dialogs.reply",
    }
    required = permission_by_endpoint.get(request.endpoint or "")
    if required is None or not has_permission(current_user, required):
        abort(403)



def _client_data(client: Client) -> dict[str, object]:
    return {"id": client.id, "name": client.name, "email": client.email, "phone": client.phone}


def _employee_data(employee: Employee) -> dict[str, object]:
    return {"id": employee.id, "name": employee.name, "email": employee.email, "position": employee.position, "is_active": employee.is_active}


def _dialog_data(dialog: Dialog) -> dict[str, object]:
    return {"id": dialog.id, "client_id": dialog.client_id, "responsible_employee_id": dialog.responsible_employee_id, "subject": dialog.subject, "status": dialog.status.value, "channel": dialog.channel}


def _message_data(message: Message) -> dict[str, object]:
    return {"id": message.id, "dialog_id": message.dialog_id, "author_type": message.author_type.value, "author_id": message.author_id, "text": message.text, "deleted_at": message.deleted_at.isoformat() if message.deleted_at else None, "is_internal": message.is_internal}


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
    if request.method == "GET":
        return jsonify([_client_data(item) for item in db.session.scalars(select(Client).order_by(Client.id))]), 200
    data = request.get_json(silent=True) or {}
    if not data.get("name") or not data.get("email"):
        return jsonify(error="name and email are required"), 400
    client = client_service.create_client(str(data["name"]), str(data["email"]), data.get("phone"))
    return jsonify(_client_data(client)), 201


@api_bp.route("/employees", methods=["GET", "POST"])
def employees() -> ResponseReturnValue:
    if request.method == "GET":
        return jsonify([_employee_data(item) for item in db.session.scalars(select(Employee).order_by(Employee.id))]), 200
    data = request.get_json(silent=True) or {}
    if not all(data.get(field) for field in ("name", "email", "password")):
        return jsonify(error="name, email and password are required"), 400
    employee = employee_service.create_employee(str(data["name"]), str(data["email"]), str(data.get("position", "Специалист поддержки")), str(data["password"]), bool(data.get("is_active", True)))
    return jsonify(_employee_data(employee)), 201


@api_bp.route("/dialogs", methods=["GET", "POST"])
def dialogs() -> ResponseReturnValue:
    if request.method == "GET":
        return jsonify([_dialog_data(item) for item in db.session.scalars(select(Dialog).order_by(Dialog.id))]), 200
    data = request.get_json(silent=True) or {}
    if not data.get("client_id") or not data.get("subject"):
        return jsonify(error="client_id and subject are required"), 400
    dialog = dialog_service.create_dialog(int(data["client_id"]), data.get("responsible_employee_id"), str(data["subject"]), str(data.get("channel", "API")))
    return jsonify(_dialog_data(dialog)), 201


@api_bp.get("/dialogs/<int:dialog_id>")
def dialog_detail(dialog_id: int) -> ResponseReturnValue:
    dialog = db.get_or_404(Dialog, dialog_id)
    return jsonify(_dialog_data(dialog)), 200


@api_bp.route("/dialogs/<int:dialog_id>/messages", methods=["GET", "POST"])
def messages(dialog_id: int) -> ResponseReturnValue:
    dialog = db.get_or_404(Dialog, dialog_id)
    if request.method == "GET":
        visible_messages = [
            item for item in dialog.messages
            if not item.is_internal or has_permission(current_user, "dialogs.add_internal_note")
        ]
        return jsonify([_message_data(item) for item in visible_messages]), 200
    data = request.get_json(silent=True) or {}
    if not data.get("text"):
        return jsonify(error="text is required"), 400
    is_internal = bool(data.get("is_internal", False))
    required = "dialogs.add_internal_note" if is_internal else "dialogs.reply"
    if not has_permission(current_user, required):
        abort(403)
    message = message_service.create_message(
        dialog.id,
        AuthorType.EMPLOYEE,
        current_user.id,
        str(data["text"]),
        is_internal=is_internal,
    )
    return jsonify(_message_data(message)), 201
