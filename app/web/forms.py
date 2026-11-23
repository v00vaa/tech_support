"""Flask-WTF forms for the browser prototype."""

from flask_wtf import FlaskForm
from flask_wtf.file import MultipleFileField
from wtforms import (
    BooleanField,
    HiddenField,
    IntegerField,
    PasswordField,
    SelectField,
    SelectMultipleField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Email, EqualTo, Length, NumberRange, Optional

from app.models.dialog import DialogStatus


class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Пароль", validators=[DataRequired()])
    submit = SubmitField("Войти")


class ClientLoginForm(FlaskForm):
    """Credentials form for customer accounts."""

    login = StringField("Логин", validators=[DataRequired(), Length(min=3, max=80)])
    password = PasswordField("Пароль", validators=[DataRequired()])
    submit = SubmitField("Войти")


class ClientDialogForm(FlaskForm):
    """Form for creating a support request from the customer portal."""

    subject = StringField("Тема обращения", validators=[DataRequired(), Length(max=255)])
    message = TextAreaField("Сообщение", validators=[DataRequired(), Length(max=10000)])
    attachments = MultipleFileField("Файлы и изображения")
    submit = SubmitField("Создать обращение")


class ClientReplyForm(FlaskForm):
    """Customer reply form without any internal-note controls."""

    text = TextAreaField("Сообщение", validators=[DataRequired(), Length(max=10000)])
    attachments = MultipleFileField("Файлы и изображения")
    submit = SubmitField("Отправить")


class ClientRegistrationForm(FlaskForm):
    """Customer registration fields; enabled contact methods are validated by the route."""

    login = StringField("Логин", validators=[DataRequired(), Length(min=3, max=80)])
    name = StringField("Имя для обращений", validators=[Optional(), Length(max=120)])
    email = StringField("Email для связи", validators=[Optional(), Email(), Length(max=255)])
    phone = StringField("Телефон для связи", validators=[Optional(), Length(max=40)])
    password = PasswordField("Пароль", validators=[DataRequired(), Length(min=8, max=128)])
    confirm_password = PasswordField(
        "Повторите пароль",
        validators=[DataRequired(), EqualTo("password", message="Пароли не совпадают.")],
    )
    submit = SubmitField("Создать аккаунт")


class GeneralSettingsForm(FlaskForm):
    """Global retention policy for closed support dialogs."""

    closed_dialog_retention_days = SelectField(
        "Срок хранения закрытых обращений",
        choices=[
            ("", "Никогда"),
            ("30", "30 дней"),
            ("90", "90 дней"),
            ("180", "180 дней"),
            ("365", "365 дней"),
        ],
    )
    submit = SubmitField("Сохранить настройки")


class WebChannelSettingsForm(FlaskForm):
    """Enable or pause intake through the customer web portal."""

    web_channel_enabled = BooleanField("Принимать новые обращения через веб-кабинет")
    submit = SubmitField("Сохранить настройки")


class RegistrationSettingsForm(FlaskForm):
    """Administrator-controlled customer registration options."""

    automatic_enabled = BooleanField("Автоматическая регистрация")
    manual_enabled = BooleanField("Ручная регистрация")
    email_enabled = BooleanField("Электронная почта")
    phone_enabled = BooleanField("Телефон")
    collect_request_details = BooleanField("Запрашивать дополнительные данные для обращений")
    submit = SubmitField("Сохранить настройки")


class ChangePasswordForm(FlaskForm):
    current_password = PasswordField("Текущий пароль", validators=[DataRequired()])
    new_password = PasswordField(
        "Новый пароль", validators=[DataRequired(), Length(min=12, max=128)]
    )
    confirm_password = PasswordField(
        "Повторите новый пароль",
        validators=[DataRequired(), EqualTo("new_password", message="Пароли не совпадают.")],
    )
    submit = SubmitField("Изменить пароль")


class ClientForm(FlaskForm):
    name = StringField("Имя", validators=[DataRequired(), Length(max=120)])
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=255)])
    phone = StringField("Телефон", validators=[Optional(), Length(max=40)])
    submit = SubmitField("Сохранить")


class EmployeeForm(FlaskForm):
    name = StringField("Имя", validators=[DataRequired(), Length(max=120)])
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=255)])
    position = StringField("Должность", validators=[DataRequired(), Length(max=120)])
    password = PasswordField("Пароль для входа", validators=[Optional(), Length(min=6, max=128)])
    is_active = BooleanField("Активен", default=True)
    submit = SubmitField("Сохранить")


class EmployeeInvitationForm(FlaskForm):
    """Create a time-limited invitation for a new employee."""

    name = StringField("Имя", validators=[DataRequired(), Length(max=120)])
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=255)])
    role_id = SelectField("Основная роль", coerce=int, validators=[DataRequired()])
    position = StringField(
        "Должность",
        validators=[DataRequired(), Length(max=120)],
        default="Специалист поддержки",
    )
    submit = SubmitField("Отправить приглашение")


class EmployeeInvitationAcceptForm(FlaskForm):
    """Set the initial password using a valid employee invitation."""

    password = PasswordField(
        "Пароль",
        validators=[DataRequired(), Length(min=12, max=128)],
    )
    confirm_password = PasswordField(
        "Повторите пароль",
        validators=[DataRequired(), EqualTo("password", message="Пароли не совпадают.")],
    )
    submit = SubmitField("Создать аккаунт")


class EmployeeRolesForm(FlaskForm):
    roles = SelectMultipleField("Роли", coerce=int)
    submit = SubmitField("Сохранить роли")


class RoleFirstLineForm(FlaskForm):
    """Select or clear the first-line support role."""

    is_first_line = BooleanField("Первый уровень поддержки")


class RoleMemberForm(FlaskForm):
    employee_id = SelectField("Сотрудник", coerce=int, validators=[DataRequired()])
    submit = SubmitField("Добавить")


class RoleMemberRemoveForm(FlaskForm):
    employee_id = HiddenField(validators=[DataRequired()])
    submit = SubmitField("Убрать")


class DialogRouteForm(FlaskForm):
    target_role_id = SelectField("Передать в роль", coerce=int, validators=[DataRequired()])
    submit = SubmitField("Передать")


class RoleRouteForm(FlaskForm):
    target_role_id = SelectField("Направлять к роли", coerce=int, validators=[DataRequired()])
    is_default = BooleanField("Маршрут по умолчанию")
    auto_forward_after_minutes = IntegerField(
        "Автоматически передать через (минут)",
        validators=[Optional(), NumberRange(min=1, max=10080)],
    )
    submit = SubmitField("Сохранить маршрут")


class WorkflowRouteForm(FlaskForm):
    """Configure a role-to-role transition in the support workflow."""

    source_role_id = SelectField("Исходная роль", coerce=int, validators=[DataRequired()])
    target_role_id = SelectField("Целевая роль", coerce=int, validators=[DataRequired()])
    is_default = BooleanField("Маршрут по умолчанию")
    auto_forward_after_minutes = IntegerField(
        "Автопередача через (минут)",
        validators=[Optional(), NumberRange(min=1, max=10080)],
    )
    submit = SubmitField("Сохранить маршрут")


class ModerationSettingsForm(FlaskForm):
    blocked_words = TextAreaField(\n        "Запрещённые слова и фразы", validators=[Optional(), Length(max=50000)]\n    )
    invalid_message_examples = TextAreaField(\n        "Примеры некорректных сообщений", validators=[Optional(), Length(max=50000)]\n    )
    submit = SubmitField("Сохранить настройки модерации")


class OllamaSettingsForm(FlaskForm):
    ollama_base_url = StringField(\n        "Адрес Ollama API", validators=[DataRequired(), Length(max=255)]\n    )
    ollama_model = StringField("Модель", validators=[DataRequired(), Length(max=120)])
    ollama_system_prompt = TextAreaField(\n        "Системный промт", validators=[DataRequired(), Length(max=20000)]\n    )
    ollama_classification_prompt = TextAreaField(\n        "Промт классификации", validators=[DataRequired(), Length(max=20000)]\n    )
    save_settings = SubmitField("Сохранить настройки")
    test_connection = SubmitField("Проверить подключение")


class RoleRouteDeleteForm(FlaskForm):
    submit = SubmitField("Удалить")


class RolePermissionsForm(FlaskForm):
    permissions = SelectMultipleField("Разрешения", coerce=str)
    submit = SubmitField("Сохранить разрешения")


class RoleForm(FlaskForm):
    name = StringField("Название", validators=[DataRequired(), Length(max=120)])
    description = TextAreaField("Описание", validators=[Optional(), Length(max=500)])
    permissions = SelectMultipleField("Разрешения", coerce=str)
    is_active = BooleanField("Роль активна", default=True)
    submit = SubmitField("Сохранить")


class DialogEditForm(FlaskForm):
    """Edit basic metadata of an existing dialog without changing its queue."""

    client_id = SelectField("Клиент", coerce=int, validators=[DataRequired()])
    responsible_employee_id = SelectField("Ответственный", coerce=int, validators=[Optional()])
    subject = StringField("Тема", validators=[DataRequired(), Length(max=255)])
    channel = SelectField("Канал", validators=[DataRequired()])
    submit = SubmitField("Сохранить")


class MessageForm(FlaskForm):
    text = TextAreaField("Сообщение", validators=[DataRequired(), Length(max=10000)])
    attachments = MultipleFileField("Файлы и изображения")
    is_internal = BooleanField("Внутренняя заметка")
    submit = SubmitField("Отправить")


class StatusForm(FlaskForm):
    status = SelectField(
        "Статус",
        choices=[(item.value, item.value.replace("_", " ").title()) for item in DialogStatus],
    )
    submit = SubmitField("Изменить")


class AssignForm(FlaskForm):
    responsible_employee_id = SelectField("Ответственный", coerce=int, validators=[Optional()])
    submit = SubmitField("Назначить")
