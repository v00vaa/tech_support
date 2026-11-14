"""Browser routes split into compact entity blueprints."""

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    make_response,
    redirect,
    render_template,
    request,
    url_for,
)
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import func

from app.extensions import db
from app.models import (
    AuthorType,
    Client,
    Dialog,
    DialogStatus,
    Employee,
    Message,
    Permission,
    RegistrationSettings,
    Role,
    RoleRoute,
)
from app.services import client_service, dialog_service, employee_service, message_service
from app.services.registration_provider import (
    RegistrationProviderError,
    RegistrationTokenInvalid,
    get_registration_provider,
)
from app.services.access_control_service import (
    can_delegate_permissions,
    has_permission,
    permission_required,
)
from app.services.routing_service import (
    delete_role_route,
    route_dialog_to_role,
    save_role_route,
)
from app.services.role_service import (
    assign_employee_roles,
    can_manage_role_members,
    manage_role_members,
    save_role,
    update_role_permissions,
    update_employee_active_state,
)
from app.web.forms import (
    AssignForm,
    ChangePasswordForm,
    ClientForm,
    ClientRegistrationForm,
    DialogForm,
    DialogRouteForm,
    EmployeeForm,
    EmployeeRolesForm,
    LoginForm,
    MessageForm,
    RegistrationSettingsForm,
    RoleForm,
    RoleMemberForm,
    RoleMemberRemoveForm,
    RolePermissionsForm,
    RoleRouteDeleteForm,
    RoleRouteForm,
    StatusForm,
)

main_bp = Blueprint("main", __name__)
auth_bp = Blueprint("auth", __name__)
clients_bp = Blueprint("clients", __name__, url_prefix="/clients")
employees_bp = Blueprint("employees", __name__, url_prefix="/employees")
dialogs_bp = Blueprint("dialogs", __name__, url_prefix="/dialogs")
messages_bp = Blueprint("messages", __name__, url_prefix="/messages")
settings_bp = Blueprint("settings", __name__, url_prefix="/settings")


def _dialog_form(form: DialogForm) -> None:
    form.client_id.choices = [
        (client.id, client.name)
        for client in db.session.scalars(db.select(Client).order_by(Client.name))
    ]
    form.responsible_employee_id.choices = [(0, "Не назначен")] + [
        (employee.id, employee.name)
        for employee in db.session.scalars(
            db.select(Employee).where(Employee.is_active).order_by(Employee.name)
        )
    ]


def _assign_form(form: AssignForm) -> None:
    form.responsible_employee_id.choices = [(0, "Не назначен")] + [
        (employee.id, employee.name)
        for employee in db.session.scalars(
            db.select(Employee).where(Employee.is_active).order_by(Employee.name)
        )
    ]


@main_bp.get("/")
@login_required
@permission_required("dialogs.view")
def index() -> ResponseReturnValue:
    stats = {
        "clients": db.session.scalar(db.select(func.count()).select_from(Client)) or 0,
        "employees": db.session.scalar(db.select(func.count()).select_from(Employee)) or 0,
        "open": db.session.scalar(
            db.select(func.count()).select_from(Dialog).where(Dialog.status == DialogStatus.OPEN)
        )
        or 0,
        "in_progress": db.session.scalar(
            db.select(func.count())
            .select_from(Dialog)
            .where(Dialog.status == DialogStatus.IN_PROGRESS)
        )
        or 0,
        "closed": db.session.scalar(
            db.select(func.count()).select_from(Dialog).where(Dialog.status == DialogStatus.CLOSED)
        )
        or 0,
    }
    return render_template("index.html", stats=stats)


def _get_registration_settings() -> RegistrationSettings:
    """Return the singleton registration settings row, creating defaults if needed."""
    settings = db.session.get(RegistrationSettings, 1)
    if settings is None:
        settings = RegistrationSettings(id=1)
        db.session.add(settings)
        db.session.commit()
    return settings


def _load_external_client(token: str) -> dict[str, str | None]:
    """Fetch the profile from the configured main-system adapter."""
    try:
        profile = get_registration_provider().get_profile(token)
    except RegistrationTokenInvalid:
        abort(400, description="Ссылка регистрации недействительна или устарела.")
    except RegistrationProviderError:
        current_app.logger.exception("Main-system registration profile request failed")
        abort(503, description="Сервис основной системы временно недоступен.")
    return {
        "external_id": profile.external_id,
        "name": profile.name,
        "email": profile.email,
        "phone": profile.phone,
    }


def _redeem_registration_token(token: str, external_id: str) -> bool:
    """Redeem after local account creation; the provider operation must be idempotent."""
    try:
        get_registration_provider().redeem_token(
            token,
            idempotency_key=f"support-client-{external_id}",
        )
    except RegistrationTokenInvalid:
        current_app.logger.warning(
            "Registration token redemption rejected for external client %s", external_id
        )
        return False
    except RegistrationProviderError:
        current_app.logger.exception(
            "Could not redeem registration token for external client %s", external_id
        )
        return False
    return True


@auth_bp.route("/register", methods=["GET", "POST"])
def client_register() -> ResponseReturnValue:
    """Register a client manually or confirm a profile fetched from the main system."""
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    settings = _get_registration_settings()
    token = (request.args.get("token") or "").strip()
    automatic_mode = bool(token)

    if automatic_mode and not settings.automatic_enabled:
        abort(404)
    if not automatic_mode and not settings.manual_enabled:
        abort(404)

    external_client = _load_external_client(token) if automatic_mode else None
    form = ClientRegistrationForm()
    if external_client and request.method == "GET":
        form.name.data = external_client["name"] or ""
        form.email.data = external_client["email"] or ""
        form.phone.data = external_client["phone"] or ""

    existing_client = None
    if external_client:
        existing_client = db.session.scalar(
            db.select(Client).where(Client.external_id == external_client["external_id"])
        )

    if existing_client is not None:
        if _redeem_registration_token(token, str(external_client["external_id"])):
            flash(
                "Этот профиль уже зарегистрирован. Ссылка регистрации больше не действует.",
                "info",
            )
        else:
            flash(
                "Аккаунт уже создан, но подтвердить использование ссылки в основной системе "
                "не удалось. Повторите попытку позже или обратитесь к администратору.",
                "warning",
            )
        return redirect(url_for("auth.client_registration_complete"))

    if form.validate_on_submit():
        errors: list[str] = []
        email = (form.email.data or "").strip().lower() if settings.email_enabled else None
        phone = (form.phone.data or "").strip() if settings.phone_enabled else None
        if not email and not phone:
            errors.append("Укажите хотя бы один доступный способ связи.")
        if email and db.session.scalar(
            db.select(Client).where(func.lower(Client.email) == email)
        ):
            errors.append("Этот email уже используется.")
        if phone and db.session.scalar(db.select(Client).where(Client.phone == phone)):
            errors.append("Этот телефон уже используется.")

        login_value = (form.login.data or "").strip().casefold()
        if db.session.scalar(db.select(Client).where(func.lower(Client.login) == login_value)):
            errors.append("Этот логин уже используется.")

        request_name = (form.name.data or "").strip()
        if settings.collect_request_details and not request_name:
            errors.append("Укажите имя для обращений.")

        if errors:
            form.login.errors = [*form.login.errors, *[e for e in errors if "логин" in e.lower()]]
            form.email.errors = [*form.email.errors, *[e for e in errors if "email" in e.lower()]]
            form.phone.errors = [*form.phone.errors, *[e for e in errors if "телефон" in e.lower()]]
            form.name.errors = [*form.name.errors, *[e for e in errors if "имя" in e.lower()]]
            if any("способ связи" in e for e in errors):
                target = form.email if settings.email_enabled else form.phone
                target.errors = [*target.errors, "Укажите хотя бы один доступный способ связи."]
        else:
            if automatic_mode and not external_client:
                abort(400)

            name = request_name if settings.collect_request_details else login_value
            client = Client(
                name=name,
                login=login_value,
                email=email,
                phone=phone,
                external_id=external_client["external_id"] if external_client else None,
            )
            client.set_password(form.password.data)
            db.session.add(client)
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
                raise

            if automatic_mode and not _redeem_registration_token(
                token, str(external_client["external_id"])
            ):
                flash(
                    "Аккаунт создан, но основная система пока не подтвердила использование "
                    "ссылки. Не создавайте повторный аккаунт; обратитесь к администратору.",
                    "warning",
                )
            else:
                flash(
                    "Аккаунт клиента создан. Вход в клиентский кабинет будет доступен "
                    "после подключения клиентской авторизации.",
                    "success",
                )
            # Do not keep the bearer token in the address bar after the POST.
            return redirect(url_for("auth.client_registration_complete"))

    response = make_response(
        render_template(
            "auth/register.html",
            form=form,
            settings=settings,
            external_client=external_client,
            automatic_mode=automatic_mode,
            already_registered=False,
        )
    )
    response.headers["Cache-Control"] = "no-store, private"
    response.headers["Pragma"] = "no-cache"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@auth_bp.get("/register/complete")
def client_registration_complete() -> ResponseReturnValue:
    """Show registration result without redirecting customers to employee login."""
    response = make_response(render_template("auth/registration_complete.html"))
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


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
    return render_template(
        "auth/login.html",
        form=form,
        registration_settings=_get_registration_settings(),
        registration_demo_enabled=(
            current_app.config["REGISTRATION_PROVIDER_MODE"] == "mock"
        ),
    )


@auth_bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password() -> ResponseReturnValue:
    form = ChangePasswordForm()
    if form.validate_on_submit():
        if not current_user.check_password(form.current_password.data):
            form.current_password.errors = [
                *form.current_password.errors,
                "Текущий пароль указан неверно.",
            ]
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
def client_list() -> ResponseReturnValue:
    clients = db.session.scalars(db.select(Client).order_by(Client.name)).all()
    return render_template("clients/list.html", clients=clients)


@clients_bp.route("/create", methods=["GET", "POST"])
@login_required
@permission_required("clients.create")
def client_create() -> ResponseReturnValue:
    form = ClientForm()
    if form.validate_on_submit():
        assert form.name.data is not None
        assert form.email.data is not None

        client_service.create_client(
            form.name.data,
            form.email.data,
            form.phone.data,
        )
        flash("Клиент создан.", "success")
        return redirect(url_for("clients.client_list"))
    return render_template("clients/create.html", form=form)


@clients_bp.get("/<int:client_id>")
@login_required
@permission_required("clients.view")
def client_detail(client_id: int) -> ResponseReturnValue:
    return render_template("clients/detail.html", client=db.get_or_404(Client, client_id))


@clients_bp.route("/<int:client_id>/edit", methods=["GET", "POST"])
@login_required
@permission_required("clients.edit")
def client_edit(client_id: int) -> ResponseReturnValue:
    client = db.get_or_404(Client, client_id)
    form = ClientForm(obj=client)
    if form.validate_on_submit():
        assert form.name.data is not None
        assert form.email.data is not None

        client_service.update_client(
            client,
            form.name.data,
            form.email.data,
            form.phone.data,
        )
        flash("Клиент изменен.", "success")
        return redirect(url_for("clients.client_detail", client_id=client.id))
    return render_template("clients/edit.html", form=form, client=client)


@clients_bp.post("/<int:client_id>/delete")
@login_required
@permission_required("clients.delete")
def client_delete(client_id: int) -> ResponseReturnValue:
    client_service.delete_client(db.get_or_404(Client, client_id))
    flash("Клиент удален.", "info")
    return redirect(url_for("clients.client_list"))


@employees_bp.get("")
@login_required
@permission_required("employees.view")
def employee_list() -> ResponseReturnValue:
    employees = db.session.scalars(db.select(Employee).order_by(Employee.name)).all()
    return render_template("employees/list.html", employees=employees)


@employees_bp.route("/create", methods=["GET", "POST"])
@login_required
@permission_required("employees.create")
def employee_create() -> ResponseReturnValue:
    form = EmployeeForm()
    if form.validate_on_submit():
        if not form.password.data:
            form.password.errors = [
                *form.password.errors,
                "Укажите пароль.",
            ]
        else:
            assert form.name.data is not None
            assert form.email.data is not None
            assert form.position.data is not None

            employee_service.create_employee(
                form.name.data,
                form.email.data,
                form.position.data,
                form.password.data,
                form.is_active.data,
            )
            flash("Сотрудник создан.", "success")
            return redirect(url_for("employees.employee_list"))
    return render_template("employees/create.html", form=form)


@employees_bp.get("/<int:employee_id>")
@login_required
@permission_required("employees.view")
def employee_detail(employee_id: int) -> ResponseReturnValue:
    return render_template("employees/detail.html", employee=db.get_or_404(Employee, employee_id))


@employees_bp.route("/<int:employee_id>/edit", methods=["GET", "POST"])
@login_required
@permission_required("employees.edit")
def employee_edit(employee_id: int) -> ResponseReturnValue:
    employee = db.get_or_404(Employee, employee_id)
    form = EmployeeForm(obj=employee)
    if form.validate_on_submit():
        assert form.name.data is not None
        assert form.email.data is not None
        assert form.position.data is not None
        try:
            employee.name = form.name.data
            employee.email = form.email.data
            employee.position = form.position.data
            update_employee_active_state(employee, form.is_active.data)
            flash("Сотрудник изменен.", "success")
            return redirect(url_for("employees.employee_detail", employee_id=employee.id))
        except ValueError as error:
            db.session.rollback()
            form.is_active.errors = [
                *form.is_active.errors,
                str(error),
            ]
    return render_template("employees/edit.html", form=form, employee=employee)


@employees_bp.post("/<int:employee_id>/delete")
@login_required
@permission_required("employees.deactivate")
def employee_delete(employee_id: int) -> ResponseReturnValue:
    employee = db.get_or_404(Employee, employee_id)
    if employee.id == current_user.id:
        flash("Нельзя отключить текущего пользователя.", "danger")
    else:
        try:
            update_employee_active_state(employee, False)
            flash("Сотрудник отключен.", "info")
        except ValueError as error:
            db.session.rollback()
            flash(str(error), "danger")
    return redirect(url_for("employees.employee_list"))


@dialogs_bp.get("")
@login_required
@permission_required("dialogs.view")
def dialog_list() -> ResponseReturnValue:
    dialogs = db.session.scalars(db.select(Dialog).order_by(Dialog.updated_at.desc())).all()
    return render_template("dialogs/list.html", dialogs=dialogs)


@dialogs_bp.route("/create", methods=["GET", "POST"])
@login_required
@permission_required("dialogs.create")
def dialog_create() -> ResponseReturnValue:
    form = DialogForm()
    _dialog_form(form)
    if form.validate_on_submit():
        assert form.client_id.data is not None
        assert form.subject.data is not None
        assert form.channel.data is not None

        dialog = dialog_service.create_dialog(
            form.client_id.data,
            form.responsible_employee_id.data or None,
            form.subject.data,
            form.channel.data,
        )
        flash("Диалог создан.", "success")
        return redirect(url_for("dialogs.dialog_detail", dialog_id=dialog.id))
    return render_template("dialogs/create.html", form=form)


@dialogs_bp.get("/<int:dialog_id>")
@login_required
@permission_required("dialogs.view")
def dialog_detail(dialog_id: int) -> ResponseReturnValue:
    dialog = db.get_or_404(Dialog, dialog_id)
    message_form, status_form, assign_form = MessageForm(), StatusForm(), AssignForm()
    status_form.status.data = dialog.status.value
    assign_form.responsible_employee_id.data = dialog.responsible_employee_id or 0
    _assign_form(assign_form)
    visible_messages = [
        message
        for message in dialog.messages
        if not message.is_internal or has_permission(current_user, "dialogs.add_internal_note")
    ]
    route_form = DialogRouteForm()
    if dialog.assigned_role_id is None:
        route_targets = db.session.scalars(
            db.select(Role).where(
                Role.role_type == "MAIN", Role.is_active, Role.code != "administrator"
            ).order_by(Role.name)
        ).all()
    else:
        route_targets = [
            route.target_role for route in dialog.assigned_role.outgoing_routes
            if route.target_role.is_active
        ]
    route_form.target_role_id.choices = [(item.id, item.name) for item in route_targets]
    return render_template(
        "dialogs/detail.html",
        dialog=dialog,
        messages=visible_messages,
        message_form=message_form,
        status_form=status_form,
        assign_form=assign_form,
        route_form=route_form,
    )


@dialogs_bp.route("/<int:dialog_id>/edit", methods=["GET", "POST"])
@login_required
@permission_required("dialogs.manage")
def dialog_edit(dialog_id: int) -> ResponseReturnValue:
    dialog = db.get_or_404(Dialog, dialog_id)
    form = DialogForm(obj=dialog)
    _dialog_form(form)
    if form.validate_on_submit():
        assert form.client_id.data is not None
        assert form.subject.data is not None
        dialog_service.update_dialog(
            dialog,
            form.client_id.data,
            form.responsible_employee_id.data or None,
            form.subject.data,
            form.channel.data,
        )
        flash("Диалог изменен.", "success")
        return redirect(url_for("dialogs.dialog_detail", dialog_id=dialog.id))
    return render_template("dialogs/edit.html", form=form, dialog=dialog)


@dialogs_bp.post("/<int:dialog_id>/delete")
@login_required
@permission_required("dialogs.manage")
def dialog_delete(dialog_id: int) -> ResponseReturnValue:
    dialog_service.delete_dialog(db.get_or_404(Dialog, dialog_id))
    flash("Диалог удален.", "info")
    return redirect(url_for("dialogs.dialog_list"))


@dialogs_bp.post("/<int:dialog_id>/status")
@login_required
@permission_required("dialogs.change_status")
def dialog_status(dialog_id: int) -> ResponseReturnValue:
    dialog, form = db.get_or_404(Dialog, dialog_id), StatusForm()
    if form.validate_on_submit():
        try:
            dialog_service.change_status(dialog, DialogStatus(form.status.data))
            flash("Статус изменен.", "success")
        except ValueError as error:
            flash(str(error), "danger")
    return redirect(url_for("dialogs.dialog_detail", dialog_id=dialog.id))


@dialogs_bp.post("/<int:dialog_id>/route")
@login_required
def dialog_route(dialog_id: int) -> ResponseReturnValue:
    dialog = db.get_or_404(Dialog, dialog_id)
    form = DialogRouteForm()
    if dialog.assigned_role_id is None:
        targets = db.session.scalars(
            db.select(Role).where(
                Role.role_type == "MAIN", Role.is_active, Role.code != "administrator"
            )
        ).all()
    else:
        targets = [item.target_role for item in dialog.assigned_role.outgoing_routes]
    form.target_role_id.choices = [(item.id, item.name) for item in targets]
    if form.validate_on_submit():
        target = db.get_or_404(Role, form.target_role_id.data)
        try:
            route_dialog_to_role(current_user, dialog, target)
            flash(f"Диалог передан в роль «{target.name}».", "success")
        except ValueError as error:
            db.session.rollback()
            flash(str(error), "danger")
    else:
        flash("Выберите допустимую роль для передачи диалога.", "danger")
    return redirect(url_for("dialogs.dialog_detail", dialog_id=dialog.id))


@dialogs_bp.post("/<int:dialog_id>/assign")
@login_required
@permission_required("dialogs.transfer")
def dialog_assign(dialog_id: int) -> ResponseReturnValue:
    dialog, form = db.get_or_404(Dialog, dialog_id), AssignForm()
    _assign_form(form)
    if form.validate_on_submit():
        dialog_service.assign_employee(dialog, form.responsible_employee_id.data or None)
        flash("Сотрудник назначен.", "success")
    return redirect(url_for("dialogs.dialog_detail", dialog_id=dialog.id))


@dialogs_bp.post("/<int:dialog_id>/messages")
@login_required
def message_create(dialog_id: int) -> ResponseReturnValue:
    dialog = db.get_or_404(Dialog, dialog_id)
    form = MessageForm()
    if form.validate_on_submit():
        assert form.text.data is not None

        is_internal = form.is_internal.data
        required_permission = "dialogs.add_internal_note" if is_internal else "dialogs.reply"
        if not has_permission(current_user, "dialogs.view") or not has_permission(
            current_user, required_permission
        ):
            from flask import abort

            abort(403)
        message_service.create_message(
            dialog.id,
            AuthorType.EMPLOYEE,
            current_user.id,
            form.text.data,
            is_internal=is_internal,
        )
        flash(
            "Внутренняя заметка добавлена." if is_internal else "Сообщение отправлено.", "success"
        )
    return redirect(url_for("dialogs.dialog_detail", dialog_id=dialog.id))


@messages_bp.route("/<int:message_id>/edit", methods=["GET", "POST"])
@login_required
@permission_required("dialogs.manage")
def message_edit(message_id: int) -> ResponseReturnValue:
    message = db.get_or_404(Message, message_id)
    form = MessageForm(obj=message)
    if form.validate_on_submit():
        assert form.text.data is not None

        message_service.update_message(message, form.text.data)
        flash("Сообщение изменено.", "success")
        return redirect(url_for("dialogs.dialog_detail", dialog_id=message.dialog_id))
    return render_template("messages/edit.html", form=form, message=message)


@messages_bp.post("/<int:message_id>/delete")
@login_required
@permission_required("dialogs.manage")
def message_delete(message_id: int) -> ResponseReturnValue:
    message = db.get_or_404(Message, message_id)
    dialog_id = message.dialog_id
    message_service.delete_message(message)
    flash("Сообщение скрыто из истории.", "info")
    return redirect(url_for("dialogs.dialog_detail", dialog_id=dialog_id))


@employees_bp.route("/<int:employee_id>/roles", methods=["GET", "POST"])
@login_required
@permission_required("employees.assign_roles")
def employee_roles_edit(employee_id: int) -> ResponseReturnValue:
    employee = db.get_or_404(Employee, employee_id)
    form = EmployeeRolesForm()
    available_roles = db.session.scalars(
        db.select(Role).where(Role.is_active).order_by(Role.name)
    ).all()
    form.roles.choices = [
        (role.id, role.name)
        for role in available_roles
        if can_delegate_permissions(
            current_user,
            {permission.code for permission in role.permissions},
        )
    ]
    if form.validate_on_submit():
        selected = (
            db.session.scalars(db.select(Role).where(Role.id.in_(form.roles.data))).all()
            if form.roles.data
            else []
        )
        try:
            assign_employee_roles(current_user, employee, selected)
            flash("Роли сотрудника обновлены.", "success")
            return redirect(url_for("employees.employee_detail", employee_id=employee.id))
        except ValueError as error:
            db.session.rollback()
            form.roles.errors = [
                *form.roles.errors,
                str(error),
            ]
    elif not form.is_submitted():
        form.roles.data = [role.id for role in employee.roles if role.is_active]
    return render_template("employees/roles.html", form=form, employee=employee)


@settings_bp.get("/roles")
@login_required
def role_list() -> ResponseReturnValue:
    all_roles = db.session.scalars(
        db.select(Role).where(Role.role_type == "MAIN").order_by(Role.is_system.desc(), Role.name)
    ).all()
    if not has_permission(current_user, "roles.view") and not any(
        can_manage_role_members(current_user, role) for role in all_roles
    ):
        abort(403)
    roles = (
        all_roles
        if has_permission(current_user, "roles.view")
        else [role for role in all_roles if can_manage_role_members(current_user, role)]
    )
    active_employees = db.session.scalars(
        db.select(Employee).where(Employee.is_active).order_by(Employee.name)
    ).all()
    member_forms = {}
    remove_forms = {}
    for role in roles:
        add_form = RoleMemberForm()
        add_form.employee_id.choices = [
            (employee.id, f"{employee.name} — {employee.email}")
            for employee in active_employees
            if role not in employee.roles
        ]
        member_forms[role.id] = add_form
        remove_forms[role.id] = {
            employee.id: RoleMemberRemoveForm(employee_id=str(employee.id))
            for employee in role.employees
        }
    global_hr = db.session.scalar(db.select(Role).where(Role.code == "global_hr"))
    return render_template(
        "settings/roles/list.html",
        roles=roles,
        member_forms=member_forms,
        remove_forms=remove_forms,
        can_manage_role_members=can_manage_role_members,
        global_hr=global_hr,
    )


@settings_bp.post("/roles/<int:role_id>/members/add")
@login_required
def role_member_add(role_id: int) -> ResponseReturnValue:
    role = db.get_or_404(Role, role_id)
    form = RoleMemberForm()
    form.employee_id.choices = [
        (employee.id, employee.name)
        for employee in db.session.scalars(
            db.select(Employee).where(Employee.is_active).order_by(Employee.name)
        )
    ]
    if not form.validate_on_submit():
        flash("Выберите сотрудника для добавления.", "danger")
        return redirect(url_for("settings.role_list"))
    employee = db.get_or_404(Employee, form.employee_id.data)
    try:
        manage_role_members(current_user, employee, role, add=True)
        flash(f"Сотрудник «{employee.name}» добавлен в роль «{role.name}».", "success")
    except ValueError as error:
        db.session.rollback()
        flash(str(error), "danger")
    return redirect(url_for("settings.role_list"))


@settings_bp.post("/roles/<int:role_id>/members/<int:employee_id>/remove")
@login_required
def role_member_remove(role_id: int, employee_id: int) -> ResponseReturnValue:
    role = db.get_or_404(Role, role_id)
    employee = db.get_or_404(Employee, employee_id)
    form = RoleMemberRemoveForm()
    if not form.validate_on_submit() or form.employee_id.data != str(employee.id):
        abort(400)
    try:
        manage_role_members(current_user, employee, role, add=False)
        flash(f"Сотрудник «{employee.name}» исключен из роли «{role.name}».", "success")
    except ValueError as error:
        db.session.rollback()
        flash(str(error), "danger")
    return redirect(url_for("settings.role_list"))


@settings_bp.get("/roles/<int:role_id>/routing/<string:direction>")
@login_required
def role_routing(role_id: int, direction: str) -> ResponseReturnValue:
    source_role = db.get_or_404(Role, role_id)
    if direction not in {"outgoing", "incoming"}:
        abort(404)
    if source_role.role_type != "MAIN" or source_role.code == "administrator":
        abort(404)
    if direction == "outgoing" and not has_permission(current_user, "roles.manage_routing"):
        abort(403)
    if direction == "incoming" and not (
        has_permission(current_user, "roles.view")
        or has_permission(current_user, "roles.manage_routing")
    ):
        abort(403)
    form = RoleRouteForm()
    main_roles = db.session.scalars(
        db.select(Role).where(
            Role.role_type == "MAIN", Role.is_active, Role.code != "administrator"
        ).order_by(Role.name)
    ).all()
    form.target_role_id.choices = [
        (item.id, item.name) for item in main_roles if item.id != source_role.id
    ]
    routes_for_view = (
        source_role.outgoing_routes if direction == "outgoing" else source_role.incoming_routes
    )
    return render_template(
        "settings/roles/routing.html",
        role=source_role,
        direction=direction,
        routes=routes_for_view,
        route_form=form,
    )


@settings_bp.post("/roles/<int:role_id>/routing/add")
@login_required
def role_routing_add(role_id: int) -> ResponseReturnValue:
    source_role = db.get_or_404(Role, role_id)
    form = RoleRouteForm()
    main_roles = db.session.scalars(
        db.select(Role).where(
            Role.role_type == "MAIN", Role.is_active, Role.code != "administrator"
        )
    ).all()
    form.target_role_id.choices = [
        (item.id, item.name) for item in main_roles if item.id != source_role.id
    ]
    if not form.validate_on_submit():
        flash("Проверьте параметры маршрута.", "danger")
        return redirect(url_for("settings.role_routing", role_id=role_id, direction="outgoing"))
    target = db.get_or_404(Role, form.target_role_id.data)
    try:
        save_role_route(
            current_user,
            source_role=source_role,
            target_role=target,
            is_default=form.is_default.data,
            auto_forward_after_minutes=form.auto_forward_after_minutes.data,
        )
        flash("Маршрут сохранен.", "success")
    except ValueError as error:
        db.session.rollback()
        flash(str(error), "danger")
    return redirect(url_for("settings.role_routing", role_id=role_id, direction="outgoing"))


@settings_bp.post("/roles/<int:role_id>/routing/<int:route_id>/delete")
@login_required
def role_routing_delete(role_id: int, route_id: int) -> ResponseReturnValue:
    source = db.get_or_404(Role, role_id)
    route = db.get_or_404(RoleRoute, route_id)
    if route.source_role_id != source.id:
        abort(404)
    form = RoleRouteDeleteForm()
    if form.validate_on_submit():
        try:
            delete_role_route(current_user, route)
            flash("Маршрут удален.", "success")
        except ValueError as error:
            db.session.rollback()
            flash(str(error), "danger")
    return redirect(url_for("settings.role_routing", role_id=role_id, direction="outgoing"))


@settings_bp.route("/roles/<int:role_id>/permissions", methods=["GET", "POST"])
@login_required
@permission_required("roles.assign_permissions")
def role_permissions_edit(role_id: int) -> ResponseReturnValue:
    role = db.get_or_404(Role, role_id)
    if role.is_system or role.role_type != "MAIN":
        abort(403)

    form = RolePermissionsForm()
    permissions = db.session.scalars(
        db.select(Permission).order_by(Permission.category, Permission.name)
    ).all()
    form.permissions.choices = [(item.code, item.name) for item in permissions]
    current_codes = {item.code for item in role.permissions}
    delegable_codes = {
        item.code for item in permissions
        if can_delegate_permissions(current_user, {item.code})
    }

    if form.validate_on_submit():
        try:
            update_role_permissions(
                current_user,
                role,
                (str(code) for code in (form.permissions.data or [])),
            )
            flash("Разрешения роли обновлены.", "success")
            return redirect(url_for("settings.role_list"))
        except ValueError as error:
            db.session.rollback()
            form.permissions.errors = [*form.permissions.errors, str(error)]
    elif not form.is_submitted():
        form.permissions.data = sorted(current_codes)

    categories = {
        "clients": "Клиенты",
        "employees": "Сотрудники",
        "roles": "Роли и доступ",
        "dialogs": "Диалоги",
        "settings": "Настройки",
    }
    grouped_permissions = []
    for category in dict.fromkeys(item.category for item in permissions):
        grouped_permissions.append(
            (
                categories.get(category, category.capitalize()),
                [item for item in permissions if item.category == category],
            )
        )

    return render_template(
        "settings/roles/permissions.html",
        role=role,
        form=form,
        permission_groups=grouped_permissions,
        current_codes=current_codes,
        delegable_codes=delegable_codes,
    )


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
        assert form.code.data is not None
        assert form.name.data is not None
        try:
            save_role(
                current_user,
                role=None,
                code=form.code.data,
                name=form.name.data,
                description=form.description.data or None,
                permission_codes=tuple(
                    str(code) for code in (form.permissions.data or []) if code is not None
                ),
                is_active=form.is_active.data,
            )
            flash("Роль создана.", "success")
            return redirect(url_for("settings.role_list"))
        except ValueError as error:
            db.session.rollback()
            form.permissions.errors = [
                *form.permissions.errors,
                str(error),
            ]
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
        assert form.code.data is not None
        assert form.name.data is not None
        try:
            save_role(
                current_user,
                role=role,
                code=form.code.data,
                name=form.name.data,
                description=form.description.data or None,
                permission_codes=tuple(
                    str(code) for code in (form.permissions.data or []) if code is not None
                ),
                is_active=form.is_active.data,
            )
            flash("Роль обновлена.", "success")
            return redirect(url_for("settings.role_list"))
        except ValueError as error:
            db.session.rollback()
            form.permissions.errors = [
                *form.permissions.errors,
                str(error),
            ]
    elif not form.is_submitted():
        form.permissions.data = [item.code for item in role.permissions]
    return render_template("settings/roles/form.html", form=form, role=role)


@settings_bp.route("/registration", methods=["GET", "POST"])
@login_required
@permission_required("settings.view")
def registration_settings() -> ResponseReturnValue:
    """Configure customer registration modes and contact channels."""
    settings = _get_registration_settings()
    form = RegistrationSettingsForm(obj=settings)

    if form.validate_on_submit():
        if not form.email_enabled.data and not form.phone_enabled.data:
            form.email_enabled.errors = [
                *form.email_enabled.errors,
                "Нужно оставить включенным хотя бы один способ связи.",
            ]
        else:
            settings.automatic_enabled = form.automatic_enabled.data
            settings.manual_enabled = form.manual_enabled.data
            settings.email_enabled = form.email_enabled.data
            settings.phone_enabled = form.phone_enabled.data
            settings.collect_request_details = form.collect_request_details.data
            db.session.commit()
            flash("Настройки регистрации сохранены.", "success")
            return redirect(url_for("settings.registration_settings"))

    return render_template("settings/registration.html", form=form, settings=settings)


@settings_bp.get("")
@login_required
@permission_required("settings.view")
def settings_index() -> ResponseReturnValue:
    return render_template("settings/index.html")


@settings_bp.get("/<string:section>")
@login_required
@permission_required("settings.view")
def settings_stub(section: str) -> ResponseReturnValue:
    labels = {
        "roles": "Роли и права",
        "workflow": "Workflow",
        "channels": "Каналы",
        "integrations": "Интеграции",
        "moderation": "Модерация",
        "ai": "AI",
        "notifications": "Уведомления",
        "company": "Интеграция с корпоративной системой",
    }
    return render_template(
        "settings/stub.html", title=labels.get(section, "Настройки"), section=section
    )
