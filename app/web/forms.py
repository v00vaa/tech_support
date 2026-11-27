"""Flask-WTF forms for the browser prototype."""

from flask_wtf import FlaskForm
from flask_wtf.file import FileField, MultipleFileField
from wtforms import (
    BooleanField,
    FloatField,
    HiddenField,
    IntegerField,
    PasswordField,
    SelectField,
    SelectMultipleField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import (
    DataRequired,
    Email,
    EqualTo,
    InputRequired,
    Length,
    NumberRange,
    Optional,
)

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


class ModerationImportForm(FlaskForm):
    """Upload a CSV or TXT file with moderation entries."""

    file = FileField("Файл CSV или TXT", validators=[DataRequired()])
    default_kind = SelectField(
        "Тип записей для TXT",
        choices=[
            ("BLOCKED_TERM", "Запрещённые фразы"),
            ("INVALID_EXAMPLE", "Примеры классификатора"),
        ],
        validators=[DataRequired()],
        default="BLOCKED_TERM",
    )
    submit = SubmitField("Импортировать")


class ModerationSettingsForm(FlaskForm):
    blocked_words_enabled = BooleanField("Включить фильтр запрещённых слов")
    classifier_enabled = BooleanField("Включить классификатор некорректных сообщений")
    moderation_event_retention_days = SelectField(
        "Срок хранения журнала модерации",
        choices=[
            ("", "Никогда"),
            ("30", "30 дней"),
            ("90", "90 дней"),
            ("180", "180 дней"),
            ("365", "365 дней"),
        ],
        validators=[Optional()],
    )
    blocked_category = StringField(
        "Категория запрещённых фраз",
        validators=[Optional(), Length(max=80)],
    )
    blocked_match_type = SelectField(
        "Способ совпадения",
        choices=[
            ("WHOLE_WORD", "Целое слово или фраза"),
            ("SUBSTRING", "Вхождение в любом месте"),
            ("EXACT", "Полное совпадение сообщения"),
        ],
        validators=[DataRequired()],
        default="WHOLE_WORD",
    )
    example_category = StringField(
        "Категория примеров классификатора",
        validators=[Optional(), Length(max=80)],
    )
    classifier_min_confidence = FloatField(
        "Минимальная уверенность для отклонения",
        validators=[InputRequired(), NumberRange(min=0, max=1)],
        default=0.75,
    )
    blocked_entries = TextAreaField(
        "Новые запрещённые слова и фразы",
        validators=[Optional(), Length(max=50000)],
    )
    example_entries = TextAreaField(
        "Новые примеры некорректных сообщений",
        validators=[Optional(), Length(max=50000)],
    )
    submit = SubmitField("Сохранить настройки модерации")


class OllamaSettingsForm(FlaskForm):
    ollama_enabled = BooleanField("Разрешить использование модели Ollama")
    ollama_base_url = StringField(
        "Адрес Ollama API",
        validators=[DataRequired(), Length(max=255)],
    )
    ollama_model = StringField("Модель", validators=[DataRequired(), Length(max=120)])
    ollama_system_prompt = TextAreaField(
        "Системный промт",
        validators=[DataRequired(), Length(max=20000)],
    )
    ollama_classification_prompt = TextAreaField(
        "Промт классификации",
        validators=[DataRequired(), Length(max=20000)],
    )
    ai_assistant_enabled = BooleanField("Включить AI-помощника для клиента")
    ai_assistant_context = TextAreaField(
        "Сведения об основной системе",
        validators=[Optional(), Length(max=20000)],
    )
    ai_assistant_prompt = TextAreaField(
        "Промт AI-помощника",
        validators=[Optional(), Length(max=20000)],
    )
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


class ModerationReviewForm(FlaskForm):
    """Record an employee decision on a moderation event."""

    review_status = SelectField(
        "Результат разбора",
        choices=[("REVIEWED", "Подтверждено"), ("IGNORED", "Отклонение ошибочно")],
        validators=[DataRequired()],
    )
    review_note = TextAreaField("Комментарий", validators=[Optional(), Length(max=2000)])
    submit = SubmitField("Сохранить разбор")
