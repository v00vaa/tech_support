"""Browser routes split into compact entity blueprints."""

from flask import Blueprint, flash, redirect, render_template, url_for
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import func

from app.extensions import db
from app.models import AuthorType, Client, Dialog, DialogStatus, Employee, Message
from app.services import client_service, dialog_service, employee_service, message_service
from app.services.access_control_service import permission_required
from app.services.role_service import (
    assign_employee_roles,
    delete_employee_safely,
    update_employee_active_state,
    save_role,
)
from app.models import Permission, Role
from app.web.forms import (
    AssignForm, ChangePasswordForm, ClientForm, DialogForm, EmployeeForm,
    EmployeeRolesForm, LoginForm, MessageForm, RoleForm, StatusForm,
)

main_bp = Blueprint("main", __name__)
auth_bp = Blueprint("auth", __name__)
clients_bp = Blueprint("clients", __name__, url_prefix="/clients")
employees_bp = Blueprint("employees", __name__, url_prefix="/employees")
dialogs_bp = Blueprint("dialogs", __name__, url_prefix="/dialogs")
messages_bp = Blueprint("messages", __name__, url_prefix="/messages")
settings_bp = Blueprint("settings", __name__, url_prefix="/settings")


def _dialog_form(form: DialogForm) -> None:
    form.client_id.choices = [(client.id, client.name) for client in db.session.scalars(db.select(Client).order_by(Client.name))]
    form.responsible_employee_id.choices = [(0, "Не назначен")] + [
        (employee.id, employee.name)
        for employee in db.session.scalars(db.select(Employee).where(Employee.is_active).order_by(Employee.name))
    ]


def _assign_form(form: AssignForm) -> None:
    form.responsible_employee_id.choices = [(0, "Не назначен")] + [
        (employee.id, employee.name)
        for employee in db.session.scalars(db.select(Employee).where(Employee.is_active).order_by(Employee.name))
    ]


@main_bp.get("/")
@login_required
@permission_required("dialogs.view")
def index() -> ResponseReturnValue:
    stats = {
        "clients": db.session.scalar(db.select(func.count()).select_from(Client)) or 0,
        "employees": db.session.scalar(db.select(func.count()).select_from(Employee)) or 0,
        "open": db.session.scalar(db.select(func.count()).select_from(Dialog).where(Dialog.status == DialogStatus.OPEN)) or 0,
        "in_progress": db.session.scalar(db.select(func.count()).select_from(Dialog).where(Dialog.status == DialogStatus.IN_PROGRESS)) or 0,
        "closed": db.session.scalar(db.select(func.count()).select_from(Dialog).where(Dialog.status == DialogStatus.CLOSED)) or 0,
    }
    return render_template("index.html", stats=stats)


@auth_bp.route("/login", methods=["GET", "POST"])
def login() -> ResponseReturnValue:
    if current_user.is_authenticated:
        if getattr(current_user, "must_change_password", False):
            return redirect(url_for("auth.change_password"))
        return redirect(url_for("main.index"))
    form = LoginForm()
    if form.validate_on_submit():
        employee = db.session.scalar(db.select(Employee).where(Employee.email == form.email.data))
        if employee and employee.is_active and employee.check_password(form.password.data):
            login_user(employee)
            flash("Вы успешно вошли в систему.", "success")
            if employee.must_change_password:
                return redirect(url_for("auth.change_password"))
            return redirect(url_for("main.index"))
        flash("Неверный email или пароль.", "danger")
    return render_template("auth/login.html", form=form)


@auth_bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password() -> ResponseReturnValue:
    form = ChangePasswordForm()
    if form.validate_on_submit():
        if not current_user.check_password(form.current_password.data):
            form.current_password.errors.append("Текущий пароль указан неверно.")
        else:
            current_user.set_password(form.new_password.data)
            current_user.must_change_password = False
            db.session.commit()
            flash("Пароль успешно изменен.", "success")
            return redirect(url_for("main.index"))
    return render_template("auth/change_password.html", form=form)


@auth_bp.post("/logout")
@login_required
def logout() -> ResponseReturnValue:
    logout_user()
    flash("Вы вышли из системы.", "info")
    return redirect(url_for("main.index"))


@clients_bp.get("")
@login_required
@permission_required("clients.view")
@login_required
def client_list() -> ResponseReturnValue:
    clients = db.session.scalars(db.select(Client).order_by(Client.name)).all()
    return render_template("clients/list.html", clients=clients)


@clients_bp.route("/create", methods=["GET", "POST"])
@login_required
@permission_required("clients.create")
@login_required
def client_create() -> ResponseReturnValue:
    form = ClientForm()
    if form.validate_on_submit():
        client_service.create_client(form.name.data, form.email.data, form.phone.data)
        flash("Клиент создан.", "success")
        return redirect(url_for("clients.client_list"))
    return render_template("clients/create.html", form=form)


@clients_bp.get("/<int:client_id>")
@login_required
@permission_required("clients.view")
@login_required
def client_detail(client_id: int) -> ResponseReturnValue:
    return render_template("clients/detail.html", client=db.get_or_404(Client, client_id))


@clients_bp.route("/<int:client_id>/edit", methods=["GET", "POST"])
@login_required
@permission_required("clients.edit")
@login_required
def client_edit(client_id: int) -> ResponseReturnValue:
    client = db.get_or_404(Client, client_id)
    form = ClientForm(obj=client)
    if form.validate_on_submit():
        client_service.update_client(client, form.name.data, form.email.data, form.phone.data)
        flash("Клиент изменен.", "success")
        return redirect(url_for("clients.client_detail", client_id=client.id))
    return render_template("clients/edit.html", form=form, client=client)


@clients_bp.post("/<int:client_id>/delete")
@login_required
@permission_required("clients.delete")
@login_required
def client_delete(client_id: int) -> ResponseReturnValue:
    client_service.delete_client(db.get_or_404(Client, client_id))
    flash("Клиент удален.", "info")
    return redirect(url_for("clients.client_list"))


@employees_bp.get("")
@login_required
@permission_required("employees.view")
@login_required
def employee_list() -> ResponseReturnValue:
    employees = db.session.scalars(db.select(Employee).order_by(Employee.name)).all()
    return render_template("employees/list.html", employees=employees)


@employees_bp.route("/create", methods=["GET", "POST"])
@login_required
@permission_required("employees.create")
@login_required
def employee_create() -> ResponseReturnValue:
    form = EmployeeForm()
    if form.validate_on_submit():
        if not form.password.data:
            form.password.errors.append("Укажите пароль.")
        else:
            employee_service.create_employee(form.name.data, form.email.data, form.position.data, form.password.data, form.is_active.data)
            flash("Сотрудник создан.", "success")
            return redirect(url_for("employees.employee_list"))
    return render_template("employees/create.html", form=form)


@employees_bp.get("/<int:employee_id>")
@login_required
@permission_required("employees.view")
@login_required
def employee_detail(employee_id: int) -> ResponseReturnValue:
    return render_template("employees/detail.html", employee=db.get_or_404(Employee, employee_id))


@employees_bp.route("/<int:employee_id>/edit", methods=["GET", "POST"])
@login_required
@permission_required("employees.edit")
@login_required
def employee_edit(employee_id: int) -> ResponseReturnValue:
    employee = db.get_or_404(Employee, employee_id)
    form = EmployeeForm(obj=employee)
    if form.validate_on_submit():
        try:
            employee.name = form.name.data
            employee.email = form.email.data
            employee.position = form.position.data
            update_employee_active_state(employee, form.is_active.data)
            flash("Сотрудник изменен.", "success")
            return redirect(url_for("employees.employee_detail", employee_id=employee.id))
        except ValueError as error:
            db.session.rollback()
            form.is_active.errors.append(str(error))
    return render_template("employees/edit.html", form=form, employee=employee)


@employees_bp.post("/<int:employee_id>/delete")
@login_required
@permission_required("employees.deactivate")
@login_required
def employee_delete(employee_id: int) -> ResponseReturnValue:
    employee = db.get_or_404(Employee, employee_id)
    if employee.id == current_user.id:
        flash("Нельзя удалить текущего пользователя.", "danger")
    else:
        try:
            delete_employee_safely(employee)
            flash("Сотрудник удален.", "info")
        except ValueError as error:
            db.session.rollback()
            flash(str(error), "danger")
    return redirect(url_for("employees.employee_list"))


@dialogs_bp.get("")
@login_required
@permission_required("dialogs.view")
@login_required
def dialog_list() -> ResponseReturnValue:
    dialogs = db.session.scalars(db.select(Dialog).order_by(Dialog.updated_at.desc())).all()
    return render_template("dialogs/list.html", dialogs=dialogs)


@dialogs_bp.route("/create", methods=["GET", "POST"])
@login_required
@permission_required("dialogs.create")
@login_required
def dialog_create() -> ResponseReturnValue:
    form = DialogForm()
    _dialog_form(form)
    if form.validate_on_submit():
        dialog = dialog_service.create_dialog(form.client_id.data, form.responsible_employee_id.data or None, form.subject.data, form.channel.data)
        flash("Диалог создан.", "success")
        return redirect(url_for("dialogs.dialog_detail", dialog_id=dialog.id))
    return render_template("dialogs/create.html", form=form)


@dialogs_bp.get("/<int:dialog_id>")
@login_required
@permission_required("dialogs.view")
@login_required
def dialog_detail(dialog_id: int) -> ResponseReturnValue:
    dialog = db.get_or_404(Dialog, dialog_id)
    message_form, status_form, assign_form = MessageForm(), StatusForm(), AssignForm()
    status_form.status.data = dialog.status.value
    assign_form.responsible_employee_id.data = dialog.responsible_employee_id or 0
    _assign_form(assign_form)
    return render_template("dialogs/detail.html", dialog=dialog, message_form=message_form, status_form=status_form, assign_form=assign_form)


@dialogs_bp.route("/<int:dialog_id>/edit", methods=["GET", "POST"])
@login_required
@permission_required("dialogs.manage")
@login_required
def dialog_edit(dialog_id: int) -> ResponseReturnValue:
    dialog = db.get_or_404(Dialog, dialog_id)
    form = DialogForm(obj=dialog)
    _dialog_form(form)
    if form.validate_on_submit():
        dialog_service.update_dialog(dialog, form.client_id.data, form.responsible_employee_id.data or None, form.subject.data, form.channel.data)
        flash("Диалог изменен.", "success")
        return redirect(url_for("dialogs.dialog_detail", dialog_id=dialog.id))
    return render_template("dialogs/edit.html", form=form, dialog=dialog)


@dialogs_bp.post("/<int:dialog_id>/delete")
@login_required
@permission_required("dialogs.manage")
@login_required
def dialog_delete(dialog_id: int) -> ResponseReturnValue:
    dialog_service.delete_dialog(db.get_or_404(Dialog, dialog_id))
    flash("Диалог удален.", "info")
    return redirect(url_for("dialogs.dialog_list"))


@dialogs_bp.post("/<int:dialog_id>/status")
@login_required
@permission_required("dialogs.manage")
@login_required
def dialog_status(dialog_id: int) -> ResponseReturnValue:
    dialog, form = db.get_or_404(Dialog, dialog_id), StatusForm()
    if form.validate_on_submit():
        try:
            dialog_service.change_status(dialog, DialogStatus(form.status.data))
            flash("Статус изменен.", "success")
        except ValueError as error:
            flash(str(error), "danger")
    return redirect(url_for("dialogs.dialog_detail", dialog_id=dialog.id))


@dialogs_bp.post("/<int:dialog_id>/assign")
@login_required
@permission_required("dialogs.transfer")
@login_required
def dialog_assign(dialog_id: int) -> ResponseReturnValue:
    dialog, form = db.get_or_404(Dialog, dialog_id), AssignForm()
    _assign_form(form)
    if form.validate_on_submit():
        dialog_service.assign_employee(dialog, form.responsible_employee_id.data or None)
        flash("Сотрудник назначен.", "success")
    return redirect(url_for("dialogs.dialog_detail", dialog_id=dialog.id))


@dialogs_bp.post("/<int:dialog_id>/messages")
@login_required
@permission_required("dialogs.reply")
@login_required
def message_create(dialog_id: int) -> ResponseReturnValue:
    dialog = db.get_or_404(Dialog, dialog_id)
    form = MessageForm()
    if form.validate_on_submit():
        message_service.create_message(
            dialog.id, AuthorType.EMPLOYEE, current_user.id, form.text.data
        )
        flash("Сообщение отправлено.", "success")
    return redirect(url_for("dialogs.dialog_detail", dialog_id=dialog.id))


@messages_bp.route("/<int:message_id>/edit", methods=["GET", "POST"])
@login_required
@permission_required("dialogs.manage")
@login_required
def message_edit(message_id: int) -> ResponseReturnValue:
    message = db.get_or_404(Message, message_id)
    form = MessageForm(obj=message)
    if form.validate_on_submit():
        message_service.update_message(message, form.text.data)
        flash("Сообщение изменено.", "success")
        return redirect(url_for("dialogs.dialog_detail", dialog_id=message.dialog_id))
    return render_template("messages/edit.html", form=form, message=message)


@messages_bp.post("/<int:message_id>/delete")
@login_required
@permission_required("dialogs.manage")
@login_required
def message_delete(message_id: int) -> ResponseReturnValue:
    message = db.get_or_404(Message, message_id)
    dialog_id = message.dialog_id
    message_service.delete_message(message)
    flash("Сообщение скрыто из истории.", "info")
    return redirect(url_for("dialogs.dialog_detail", dialog_id=dialog_id))


@employees_bp.route("/<int:employee_id>/roles", methods=["GET", "POST"])
@login_required
@permission_required("settings.view")
@login_required
@permission_required("employees.assign_roles")
def employee_roles_edit(employee_id: int) -> ResponseReturnValue:
    employee = db.get_or_404(Employee, employee_id)
    form = EmployeeRolesForm()
    available_roles = db.session.scalars(
        db.select(Role).where(Role.is_active).order_by(Role.name)
    ).all()
    form.roles.choices = [(role.id, role.name) for role in available_roles]
    if form.validate_on_submit():
        selected = db.session.scalars(
            db.select(Role).where(Role.id.in_(form.roles.data))
        ).all() if form.roles.data else []
        try:
            assign_employee_roles(current_user, employee, selected)
            flash("Роли сотрудника обновлены.", "success")
            return redirect(url_for("employees.employee_detail", employee_id=employee.id))
        except ValueError as error:
            db.session.rollback()
            form.roles.errors.append(str(error))
    elif not form.is_submitted():
        form.roles.data = [role.id for role in employee.roles if role.is_active]
    return render_template("employees/roles.html", form=form, employee=employee)


@settings_bp.get("/roles")
@login_required
@permission_required("roles.view")
def role_list() -> ResponseReturnValue:
    roles = db.session.scalars(
        db.select(Role).order_by(Role.is_system.desc(), Role.name)
    ).all()
    return render_template("settings/roles/list.html", roles=roles)


@settings_bp.route("/roles/create", methods=["GET", "POST"])
@login_required
@permission_required("roles.create")
def role_create() -> ResponseReturnValue:
    form = RoleForm()
    permissions = db.session.scalars(
        db.select(Permission).order_by(Permission.category, Permission.name)
    ).all()
    form.permissions.choices = [(item.code, f"{item.name} ({item.code})") for item in permissions]
    if form.validate_on_submit():
        try:
            save_role(
                current_user,
                role=None,
                code=form.code.data,
                name=form.name.data,
                description=form.description.data or None,
                permission_codes=form.permissions.data,
                is_active=form.is_active.data,
            )
            flash("Роль создана.", "success")
            return redirect(url_for("settings.role_list"))
        except ValueError as error:
            db.session.rollback()
            form.permissions.errors.append(str(error))
    return render_template("settings/roles/form.html", form=form, role=None)


@settings_bp.route("/roles/<int:role_id>/edit", methods=["GET", "POST"])
@login_required
@permission_required("roles.edit")
def role_edit(role_id: int) -> ResponseReturnValue:
    role = db.get_or_404(Role, role_id)
    if role.is_system:
        flash("Системные роли доступны только для просмотра.", "warning")
        return redirect(url_for("settings.role_list"))
    form = RoleForm(obj=role)
    permissions = db.session.scalars(
        db.select(Permission).order_by(Permission.category, Permission.name)
    ).all()
    form.permissions.choices = [(item.code, f"{item.name} ({item.code})") for item in permissions]
    if form.validate_on_submit():
        try:
            save_role(
                current_user,
                role=role,
                code=form.code.data,
                name=form.name.data,
                description=form.description.data or None,
                permission_codes=form.permissions.data,
                is_active=form.is_active.data,
            )
            flash("Роль обновлена.", "success")
            return redirect(url_for("settings.role_list"))
        except ValueError as error:
            db.session.rollback()
            form.permissions.errors.append(str(error))
    elif not form.is_submitted():
        form.permissions.data = [item.code for item in role.permissions]
    return render_template("settings/roles/form.html", form=form, role=role)


@settings_bp.get("")
@login_required
def settings_index() -> ResponseReturnValue:
    return render_template("settings/index.html")


@settings_bp.get("/<string:section>")
@login_required
@permission_required("settings.view")
@login_required
def settings_stub(section: str) -> ResponseReturnValue:
    labels = {
        "roles": "Роли и права", "workflow": "Workflow", "channels": "Каналы",
        "integrations": "Интеграции", "moderation": "Модерация", "ai": "AI",
        "notifications": "Уведомления", "company": "Интеграция с корпоративной системой",
    }
    return render_template("settings/stub.html", title=labels.get(section, "Настройки"), section=section)
