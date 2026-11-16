"""Browser routes split into compact entity blueprints."""

import mimetypes
import re
from collections.abc import Callable
from datetime import UTC, datetime
from functools import wraps
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    get_flashed_messages,
    make_response,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import func, update
from sqlalchemy.engine import CursorResult

from app.extensions import db
from app.models import (
    Attachment,
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
from app.services.access_control_service import (
    can_delegate_permissions,
    has_permission,
    is_active_administrator,
    permission_required,
)
from app.services.registration_provider import (
    RegistrationProviderError,
    RegistrationTokenInvalid,
    get_registration_provider,
)
from app.services.role_service import (
    assign_employee_roles,
    can_manage_role_members,
    manage_role_members,
    save_role,
    update_employee_active_state,
    update_role_permissions,
)
from app.services.routing_service import (
    delete_role_route,
    route_dialog_to_role,
    save_role_route,
)
from app.web.forms import (
    AssignForm,
    ChangePasswordForm,
    ClientDialogForm,
    ClientForm,
    ClientLoginForm,
    ClientRegistrationForm,
    ClientReplyForm,
    DialogEditForm,
    DialogRouteForm,
    EmployeeForm,
    EmployeeRolesForm,
    LoginForm,
    MessageForm,
    RegistrationSettingsForm,
    RoleForm,
    RoleFirstLineForm,
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
portal_bp = Blueprint("portal", __name__, url_prefix="/portal")


_ALLOWED_ATTACHMENT_EXTENSIONS = {
    "csv",
    "doc",
    "docx",
    "gif",
    "jpeg",
    "jpg",
    "pdf",
    "png",
    "txt",
    "webp",
    "xls",
    "xlsx",
    "zip",
}
_MAX_ATTACHMENT_SIZE = 10 * 1024 * 1024
_MAX_ATTACHMENTS_PER_MESSAGE = 5


def _store_message_attachments(message: Message, uploads: list[Any]) -> list[Path]:
    """Persist validated uploads under private instance storage, never the public static folder."""
    selected = [upload for upload in uploads if upload and upload.filename]
    if len(selected) > _MAX_ATTACHMENTS_PER_MESSAGE:
        raise ValueError(f"Можно прикрепить не более {_MAX_ATTACHMENTS_PER_MESSAGE} файлов.")

    prepared: list[tuple[Any, str, str, int, str]] = []
    for upload in selected:
        original_name = (upload.filename or "").replace("\\", "/").rsplit("/", maxsplit=1)[-1]
        filename = re.sub(r"[\\x00-\\x1f\\x7f]", "", original_name).strip()
        suffix = Path(filename).suffix.lower()
        extension = suffix.removeprefix(".")
        if not filename or extension not in _ALLOWED_ATTACHMENT_EXTENSIONS:
            raise ValueError("Недопустимый тип файла.")

        upload.stream.seek(0, 2)
        size_bytes = upload.stream.tell()
        upload.stream.seek(0)
        if size_bytes <= 0 or size_bytes > _MAX_ATTACHMENT_SIZE:
            raise ValueError("Размер каждого файла должен быть от 1 байта до 10 МБ.")
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        prepared.append((upload, filename, suffix, size_bytes, content_type))

    storage_dir = Path(current_app.instance_path) / "uploads"
    storage_dir.mkdir(parents=True, exist_ok=True)
    saved_paths: list[Path] = []
    try:
        for upload, filename, suffix, size_bytes, content_type in prepared:
            storage_key = f"{uuid4().hex}{suffix}"
            path = storage_dir / storage_key
            upload.save(path)
            saved_paths.append(path)
            db.session.add(
                Attachment(
                    message_id=message.id,
                    filename=filename[:255],
                    storage_key=storage_key,
                    content_type=content_type,
                    size_bytes=size_bytes,
                )
            )
    except Exception:
        _remove_saved_attachments(saved_paths)
        raise
    return saved_paths


def _remove_saved_attachments(paths: list[Path]) -> None:
    for path in paths:
        path.unlink(missing_ok=True)


def _dialog_edit_form(form: DialogEditForm) -> None:
    """Populate choices for editing dialog metadata without changing its queue."""
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
    configured_channels = current_app.config.get(
        "SUPPORT_CHANNELS",
        [("Web", "Веб-кабинет"), ("API", "Внешний API"), ("Widget", "Виджет")],
    )
    form.channel.choices = [(str(value), str(label)) for value, label in configured_channels]


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
        if isinstance(current_user._get_current_object(), Client):
            return redirect(url_for("portal.index"))
        return redirect(url_for("main.index"))

    settings = _get_registration_settings()
    token = (request.args.get("token") or request.form.get("registration_token") or "").strip()
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
        assert external_client is not None
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
        if email and db.session.scalar(db.select(Client).where(func.lower(Client.email) == email)):
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
            assert form.password.data is not None

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

            if (
                automatic_mode
                and external_client is not None
                and not _redeem_registration_token(token, str(external_client["external_id"]))
            ):
                flash(
                    "Аккаунт создан, но основная система пока не подтвердила использование "
                    "ссылки. Не создавайте повторный аккаунт; обратитесь к администратору.",
                    "warning",
                )
            else:
                flash(
                    "Аккаунт клиента создан. Теперь можно войти в клиентский кабинет.",
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
            registration_token=token if automatic_mode else "",
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
    messages = get_flashed_messages(with_categories=True)
    if not messages:
        return redirect(url_for("auth.client_login"))
    response = make_response(render_template("auth/registration_complete.html", messages=messages))
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


def client_required(view: Callable[..., Any]) -> Callable[..., Any]:
    """Require a logged-in customer, never an employee account."""

    @wraps(view)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        if not current_user.is_authenticated:
            return redirect(url_for("auth.client_login"))
        if not isinstance(current_user._get_current_object(), Client):
            abort(403)
        if not current_user.is_active:
            abort(403)
        return view(*args, **kwargs)

    return wrapped


@auth_bp.route("/client/login", methods=["GET", "POST"])
def client_login() -> ResponseReturnValue:
    """Authenticate a customer by their local username and password."""
    if current_user.is_authenticated:
        if isinstance(current_user._get_current_object(), Client):
            return redirect(url_for("portal.index"))
        return redirect(url_for("main.index"))

    form = ClientLoginForm()
    if form.validate_on_submit():
        login_value = (form.login.data or "").strip().casefold()
        client = db.session.scalar(db.select(Client).where(func.lower(Client.login) == login_value))
        if client and client.is_active and client.check_password(form.password.data):
            login_user(client, remember=False, fresh=True)
            flash("Вы успешно вошли в клиентский кабинет.", "success")
            return redirect(url_for("portal.index"))
        flash("Неверный логин или пароль.", "danger")

    return render_template("auth/client_login.html", form=form)


@auth_bp.route("/login", methods=["GET", "POST"])
def login() -> ResponseReturnValue:
    if current_user.is_authenticated:
        if isinstance(current_user._get_current_object(), Client):
            return redirect(url_for("portal.index"))
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
        registration_demo_enabled=(current_app.config["REGISTRATION_PROVIDER_MODE"] == "mock"),
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
    was_client = isinstance(current_user._get_current_object(), Client)
    logout_user()
    flash("Вы вышли из системы.", "info")
    return redirect(url_for("auth.client_login" if was_client else "auth.login"))


@portal_bp.get("/", endpoint="index")
@client_required
def portal_index() -> ResponseReturnValue:
    """Show only the current customer's support requests."""
    dialogs = db.session.scalars(
        db.select(Dialog)
        .where(Dialog.client_id == current_user.id)
        .order_by(Dialog.updated_at.desc())
    ).all()
    return render_template("portal/index.html", dialogs=dialogs)


@portal_bp.route("/dialogs/new", methods=["GET", "POST"], endpoint="dialog_create")
@client_required
def portal_dialog_create() -> ResponseReturnValue:
    """Create a new customer-owned dialog and its first public message."""
    form = ClientDialogForm()
    if form.validate_on_submit():
        first_line_role = db.session.scalar(
            db.select(Role).where(
                Role.is_first_line.is_(True),
                Role.is_active.is_(True),
                Role.role_type == "MAIN",
                Role.scope_role_id.is_(None),
                Role.code != "administrator",
            )
        )
        if first_line_role is None:
            flash(
                "Создание обращений временно недоступно: администратор не настроил "
                "активную роль первого уровня поддержки.",
                "danger",
            )
            return render_template("portal/dialog_form.html", form=form), 503

        now = datetime.now(UTC)
        dialog = Dialog(
            client_id=current_user.id,
            assigned_role_id=first_line_role.id,
            role_assigned_at=now,
            subject=(form.subject.data or "").strip(),
            channel="Web",
            status=DialogStatus.OPEN,
        )
        db.session.add(dialog)
        db.session.flush()
        dialog.updated_at = datetime.now(UTC)
        db.session.add(
            Message(
                dialog_id=dialog.id,
                author_type=AuthorType.SYSTEM,
                author_id=None,
                text="Обращение создано.",
                is_internal=False,
            )
        )
        message = Message(
            dialog_id=dialog.id,
            author_type=AuthorType.CLIENT,
            author_id=current_user.id,
            text=(form.message.data or "").strip(),
            is_internal=False,
        )
        db.session.add(message)
        db.session.flush()
        saved_paths: list[Path] = []
        try:
            saved_paths = _store_message_attachments(message, form.attachments.data or [])
            db.session.commit()
        except ValueError as error:
            db.session.rollback()
            _remove_saved_attachments(saved_paths)
            form.message.errors = [*form.message.errors, str(error)]
            return render_template("portal/dialog_form.html", form=form), 400
        except Exception:
            db.session.rollback()
            _remove_saved_attachments(saved_paths)
            raise
        flash("Обращение создано.", "success")
        return redirect(url_for("portal.dialog_detail", dialog_id=dialog.id))
    return render_template("portal/dialog_form.html", form=form)


@portal_bp.route("/dialogs/<int:dialog_id>", methods=["GET", "POST"], endpoint="dialog_detail")
@client_required
def portal_dialog_detail(dialog_id: int) -> ResponseReturnValue:
    """Read and reply only to a dialog owned by the authenticated customer."""
    dialog = db.session.scalar(
        db.select(Dialog).where(
            Dialog.id == dialog_id,
            Dialog.client_id == current_user.id,
        )
    )
    if dialog is None:
        abort(404)

    form = ClientReplyForm()
    if request.method == "POST":
        if dialog.status == DialogStatus.CLOSED:
            abort(403, description="Закрытое обращение нельзя продолжить.")
        if form.validate_on_submit():
            dialog.updated_at = datetime.now(UTC)
            message = Message(
                dialog_id=dialog.id,
                author_type=AuthorType.CLIENT,
                author_id=current_user.id,
                text=(form.text.data or "").strip(),
                is_internal=False,
            )
            db.session.add(message)
            db.session.flush()
            saved_paths: list[Path] = []
            try:
                saved_paths = _store_message_attachments(message, form.attachments.data or [])
                if dialog.status == DialogStatus.WAITING_CLIENT:
                    dialog.status = DialogStatus.IN_PROGRESS
                db.session.commit()
            except ValueError as error:
                db.session.rollback()
                _remove_saved_attachments(saved_paths)
                form.text.errors = [*form.text.errors, str(error)]
            except Exception:
                db.session.rollback()
                _remove_saved_attachments(saved_paths)
                raise
            else:
                flash("Сообщение отправлено.", "success")
                return redirect(url_for("portal.dialog_detail", dialog_id=dialog.id))
            flash("Сообщение отправлено.", "success")
            return redirect(url_for("portal.dialog_detail", dialog_id=dialog.id))

    before_message_id = request.args.get("before", type=int)
    message_query = db.select(Message).where(
        Message.dialog_id == dialog.id,
        Message.is_internal.is_(False),
        Message.deleted_at.is_(None),
    )
    if before_message_id:
        message_query = message_query.where(Message.id < before_message_id)
    message_batch = db.session.scalars(
        message_query.order_by(Message.id.desc()).limit(51)
    ).all()
    has_older_messages = len(message_batch) > 50
    visible_messages = list(reversed(message_batch[:50]))
    dialog_attachments = db.session.scalars(
        db.select(Attachment)
        .join(Message, Attachment.message_id == Message.id)
        .where(
            Message.dialog_id == dialog.id,
            Message.is_internal.is_(False),
            Message.deleted_at.is_(None),
        )
        .order_by(Message.id.desc(), Attachment.id.desc())
    ).all()
    client_dialogs = db.session.scalars(
        db.select(Dialog)
        .where(Dialog.client_id == current_user.id)
        .order_by(Dialog.updated_at.desc())
    ).all()
    return render_template(
        "portal/dialog_detail.html",
        dialog=dialog,
        messages=visible_messages,
        form=form,
        client_dialogs=client_dialogs,
        dialog_attachments=dialog_attachments,
        has_older_messages=has_older_messages,
    )


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
    """Show only the employee's own dialogs and queues belonging to their roles."""
    own_dialogs = db.session.scalars(
        db.select(Dialog)
        .where(Dialog.responsible_employee_id == current_user.id)
        .order_by(Dialog.updated_at.desc())
        .limit(50)
    ).all()
    queue_roles = [
        role
        for role in current_user.roles
        if role.is_active and role.role_type == "MAIN" and role.code != "administrator"
    ]
    queue_dialogs = {}
    queue_stats = {}
    for role in queue_roles:
        queue_dialogs[role.id] = db.session.scalars(
            db.select(Dialog)
            .where(
                Dialog.assigned_role_id == role.id,
                Dialog.responsible_employee_id.is_(None),
                Dialog.status.in_([DialogStatus.OPEN, DialogStatus.WAITING_EMPLOYEE]),
            )
            .order_by(Dialog.updated_at.asc())
            .limit(50)
        ).all()
        queue_stats[role.id] = {
            "waiting": db.session.scalar(
                db.select(func.count())
                .select_from(Dialog)
                .where(
                    Dialog.assigned_role_id == role.id,
                    Dialog.responsible_employee_id.is_(None),
                    Dialog.status.in_([DialogStatus.OPEN, DialogStatus.WAITING_EMPLOYEE]),
                )
            )
            or 0,
            "active": db.session.scalar(
                db.select(func.count())
                .select_from(Dialog)
                .where(
                    Dialog.assigned_role_id == role.id,
                    Dialog.status == DialogStatus.IN_PROGRESS,
                )
            )
            or 0,
        }
    return render_template(
        "dialogs/list.html",
        own_dialogs=own_dialogs,
        queue_roles=queue_roles,
        queue_dialogs=queue_dialogs,
        queue_stats=queue_stats,
    )


@dialogs_bp.get("/<int:dialog_id>")
@login_required
@permission_required("dialogs.view")
def dialog_detail(dialog_id: int) -> ResponseReturnValue:
    dialog = db.get_or_404(Dialog, dialog_id)
    message_form, status_form, assign_form = MessageForm(), StatusForm(), AssignForm()
    status_form.status.data = dialog.status.value
    assign_form.responsible_employee_id.data = dialog.responsible_employee_id or 0
    _assign_form(assign_form)
    can_view_notes = has_permission(current_user, "dialogs.add_internal_note")
    before_message_id = request.args.get("before", type=int)
    message_query = db.select(Message).where(
        Message.dialog_id == dialog.id,
        Message.is_internal.is_(False),
        Message.deleted_at.is_(None),
    )
    if before_message_id:
        message_query = message_query.where(Message.id < before_message_id)
    message_batch = db.session.scalars(
        message_query.order_by(Message.id.desc()).limit(51)
    ).all()
    has_older_messages = len(message_batch) > 50
    visible_messages = list(reversed(message_batch[:50]))
    internal_notes = (
        db.session.scalars(
            db.select(Message)
            .where(
                Message.dialog_id == dialog.id,
                Message.is_internal.is_(True),
                Message.deleted_at.is_(None),
            )
            .order_by(Message.id.desc())
            .limit(50)
        ).all()
        if can_view_notes
        else []
    )
    attachment_query = (
        db.select(Attachment)
        .join(Message, Attachment.message_id == Message.id)
        .where(
            Message.dialog_id == dialog.id,
            Message.deleted_at.is_(None),
        )
    )
    if not can_view_notes:
        attachment_query = attachment_query.where(Message.is_internal.is_(False))
    dialog_attachments = db.session.scalars(
        attachment_query.order_by(Message.id.desc(), Attachment.id.desc())
    ).all()
    own_dialogs = db.session.scalars(
        db.select(Dialog)
        .where(Dialog.responsible_employee_id == current_user.id)
        .order_by(Dialog.updated_at.desc())
        .limit(30)
    ).all()
    client_dialogs = db.session.scalars(
        db.select(Dialog)
        .where(Dialog.client_id == dialog.client_id)
        .order_by(Dialog.updated_at.desc())
    ).all()
    queue_roles = [
        role
        for role in current_user.roles
        if role.is_active and role.role_type == "MAIN" and role.code != "administrator"
    ]
    queue_stats = {}
    queue_dialogs = {}
    for role in queue_roles:
        queue_dialogs[role.id] = db.session.scalars(
            db.select(Dialog)
            .where(
                Dialog.assigned_role_id == role.id,
                Dialog.responsible_employee_id.is_(None),
                Dialog.status.in_([DialogStatus.OPEN, DialogStatus.WAITING_EMPLOYEE]),
            )
            .order_by(Dialog.updated_at.asc())
            .limit(50)
        ).all()
        queue_stats[role.id] = {
            "waiting": db.session.scalar(
                db.select(func.count())
                .select_from(Dialog)
                .where(
                    Dialog.assigned_role_id == role.id,
                    Dialog.responsible_employee_id.is_(None),
                    Dialog.status.in_([DialogStatus.OPEN, DialogStatus.WAITING_EMPLOYEE]),
                )
            )
            or 0,
            "active": db.session.scalar(
                db.select(func.count())
                .select_from(Dialog)
                .where(
                    Dialog.assigned_role_id == role.id,
                    Dialog.status == DialogStatus.IN_PROGRESS,
                )
            )
            or 0,
        }
    can_claim = (
        dialog.responsible_employee_id is None
        and dialog.assigned_role_id in {role.id for role in queue_roles}
        and dialog.status in {DialogStatus.OPEN, DialogStatus.WAITING_EMPLOYEE}
    )
    route_form = DialogRouteForm()
    if dialog.assigned_role is None:
        route_targets = []
    else:
        assigned_role = dialog.assigned_role
        route_targets = [
            route.target_role
            for route in assigned_role.outgoing_routes
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
        own_dialogs=own_dialogs,
        client_dialogs=client_dialogs,
        queue_roles=queue_roles,
        queue_stats=queue_stats,
        queue_dialogs=queue_dialogs,
        internal_notes=internal_notes,
        dialog_attachments=dialog_attachments,
        can_view_notes=can_view_notes,
        can_claim=can_claim,
        has_older_messages=has_older_messages,
    )


@dialogs_bp.route("/<int:dialog_id>/edit", methods=["GET", "POST"])
@login_required
@permission_required("dialogs.manage")
def dialog_edit(dialog_id: int) -> ResponseReturnValue:
    dialog = db.get_or_404(Dialog, dialog_id)
    form = DialogEditForm(obj=dialog)
    _dialog_edit_form(form)
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
            previous_status = dialog.status
            dialog_service.change_status(dialog, DialogStatus(form.status.data))
            if dialog.status != previous_status:
                db.session.add(
                    Message(
                        dialog_id=dialog.id,
                        author_type=AuthorType.SYSTEM,
                        author_id=None,
                        text=(
                            "Статус изменен: "
                            f"{previous_status.value.replace('_', ' ').lower()} → "
                            f"{dialog.status.value.replace('_', ' ').lower()}."
                        ),
                        is_internal=False,
                    )
                )
                db.session.commit()
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
        targets = []
    else:
        assigned_role = dialog.assigned_role
        targets = [
            item.target_role
            for item in assigned_role.outgoing_routes
            if item.target_role.is_active
        ]
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
        employee_id = form.responsible_employee_id.data or None
        employee = db.session.get(Employee, employee_id) if employee_id else None
        previous_employee_id = dialog.responsible_employee_id
        dialog_service.assign_employee(dialog, employee_id)
        if previous_employee_id != employee_id:
            db.session.add(
                Message(
                    dialog_id=dialog.id,
                    author_type=AuthorType.SYSTEM,
                    author_id=None,
                    text=(
                        f"Ответственный назначен: {employee.name}."
                        if employee is not None
                        else "Ответственный сотрудник снят."
                    ),
                    is_internal=False,
                )
            )
            db.session.commit()
        flash("Сотрудник назначен.", "success")
    return redirect(url_for("dialogs.dialog_detail", dialog_id=dialog.id))


@dialogs_bp.post("/<int:dialog_id>/claim")
@login_required
@permission_required("dialogs.view")
def dialog_claim(dialog_id: int) -> ResponseReturnValue:
    """Atomically claim an unassigned dialog from one of the employee's own role queues."""
    dialog = db.get_or_404(Dialog, dialog_id)
    role_ids = [
        role.id
        for role in current_user.roles
        if role.is_active and role.role_type == "MAIN" and role.code != "administrator"
    ]
    if not role_ids:
        abort(403)
    result = cast(
        CursorResult[Any],
        db.session.execute(
            update(Dialog)
            .where(
                Dialog.id == dialog.id,
                Dialog.assigned_role_id.in_(role_ids),
                Dialog.responsible_employee_id.is_(None),
                Dialog.status.in_([DialogStatus.OPEN, DialogStatus.WAITING_EMPLOYEE]),
            )
            .values(
                responsible_employee_id=current_user.id,
                status=DialogStatus.IN_PROGRESS,
                updated_at=datetime.now(UTC),
            )
        ),
    )
    if result.rowcount != 1:
        db.session.rollback()
        flash("Обращение уже взял другой сотрудник или оно недоступно в вашей очереди.", "warning")
    else:
        db.session.add(
            Message(
                dialog_id=dialog.id,
                author_type=AuthorType.SYSTEM,
                author_id=None,
                text="Обращение взял в работу сотрудник.",
                is_internal=False,
            )
        )
        db.session.commit()
        flash("Обращение назначено на вас.", "success")
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
        message = Message(
            dialog_id=dialog.id,
            author_type=AuthorType.EMPLOYEE,
            author_id=current_user.id,
            text=form.text.data,
            is_internal=is_internal,
        )
        db.session.add(message)
        db.session.flush()
        saved_paths: list[Path] = []
        try:
            saved_paths = _store_message_attachments(message, form.attachments.data or [])
            db.session.commit()
        except ValueError as error:
            db.session.rollback()
            _remove_saved_attachments(saved_paths)
            form.text.errors = [*form.text.errors, str(error)]
            flash(str(error), "danger")
            return redirect(url_for("dialogs.dialog_detail", dialog_id=dialog.id))
        except Exception:
            db.session.rollback()
            _remove_saved_attachments(saved_paths)
            raise
        flash(
            "Внутренняя заметка добавлена." if is_internal else "Сообщение отправлено.", "success"
        )
    return redirect(url_for("dialogs.dialog_detail", dialog_id=dialog.id))


@messages_bp.get("/attachments/<int:attachment_id>")
@login_required
def attachment_download(attachment_id: int) -> ResponseReturnValue:
    """Serve private attachments only to users allowed to see the parent message."""
    attachment = db.get_or_404(Attachment, attachment_id)
    message = attachment.message
    if message is None or message.deleted_at is not None or not attachment.storage_key:
        abort(404)

    user = current_user._get_current_object()
    if isinstance(user, Client):
        if message.is_internal or message.dialog.client_id != user.id:
            abort(404)
    else:
        if not has_permission(current_user, "dialogs.view"):
            abort(403)
        if message.is_internal and not has_permission(current_user, "dialogs.add_internal_note"):
            abort(403)

    upload_dir = (Path(current_app.instance_path) / "uploads").resolve()
    file_path = (upload_dir / attachment.storage_key).resolve()
    if upload_dir not in file_path.parents or not file_path.is_file():
        abort(404)

    is_image = attachment.content_type.startswith("image/")
    response = send_file(
        file_path,
        mimetype=attachment.content_type,
        as_attachment=not is_image,
        download_name=attachment.filename,
        conditional=True,
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "private, no-store"
    return response


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
    first_line_forms = {role.id: RoleFirstLineForm(obj=role) for role in roles}
    global_hr = db.session.scalar(db.select(Role).where(Role.code == "global_hr"))
    return render_template(
        "settings/roles/list.html",
        roles=roles,
        member_forms=member_forms,
        remove_forms=remove_forms,
        first_line_forms=first_line_forms,
        can_configure_first_line=is_active_administrator(current_user),
        can_manage_role_members=can_manage_role_members,
        global_hr=global_hr,
    )


@settings_bp.post("/roles/<int:role_id>/first-line")
@login_required
def role_first_line_update(role_id: int) -> ResponseReturnValue:
    """Allow an administrator to select the first-line support role."""
    if not is_active_administrator(current_user):
        abort(403)

    role = db.get_or_404(Role, role_id)
    form = RoleFirstLineForm()
    if not form.validate_on_submit():
        abort(400)
    if (
        role.role_type != "MAIN"
        or role.scope_role_id is not None
        or role.code == "administrator"
        or (form.is_first_line.data and not role.is_active)
    ):
        flash("Первым уровнем может быть только активная основная роль.", "danger")
        return redirect(url_for("settings.role_list"))

    try:
        if form.is_first_line.data:
            # Serialize concurrent admin selections before clearing the previous flag.
            db.session.scalars(db.select(Role.id).with_for_update()).all()
            db.session.execute(
                update(Role)
                .where(Role.is_first_line.is_(True))
                .values(is_first_line=False)
            )
        role.is_first_line = bool(form.is_first_line.data)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    flash(
        (
            f"Роль «{role.name}» назначена первым уровнем поддержки."
            if role.is_first_line
            else f"Роль «{role.name}» больше не является первым уровнем поддержки."
        ),
        "success",
    )
    return redirect(url_for("settings.role_list"))


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
        db.select(Role)
        .where(Role.role_type == "MAIN", Role.is_active, Role.code != "administrator")
        .order_by(Role.name)
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
        item.code for item in permissions if can_delegate_permissions(current_user, {item.code})
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
