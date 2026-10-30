"""Flask-WTF forms for the browser prototype."""

from flask_wtf import FlaskForm
from wtforms import BooleanField, PasswordField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Email, EqualTo, Length, Optional

from app.models.dialog import DialogStatus
from app.models.message import AuthorType


class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Пароль", validators=[DataRequired()])
    submit = SubmitField("Войти")


class ChangePasswordForm(FlaskForm):
    current_password = PasswordField("Текущий пароль", validators=[DataRequired()])
    new_password = PasswordField("Новый пароль", validators=[DataRequired(), Length(min=12, max=128)])
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


class DialogForm(FlaskForm):
    client_id = SelectField("Клиент", coerce=int, validators=[DataRequired()])
    responsible_employee_id = SelectField("Ответственный", coerce=int, validators=[Optional()])
    subject = StringField("Тема", validators=[DataRequired(), Length(max=255)])
    channel = SelectField("Канал", choices=[("Web", "Web"), ("API", "Внешний API"), ("Widget", "Виджет")])
    submit = SubmitField("Сохранить")


class MessageForm(FlaskForm):
    text = TextAreaField("Сообщение", validators=[DataRequired(), Length(max=10000)])
    author_type = SelectField("Автор", choices=[(item.value, item.value.title()) for item in AuthorType])
    submit = SubmitField("Отправить")


class StatusForm(FlaskForm):
    status = SelectField("Статус", choices=[(item.value, item.value.replace("_", " ").title()) for item in DialogStatus])
    submit = SubmitField("Изменить")


class AssignForm(FlaskForm):
    responsible_employee_id = SelectField("Ответственный", coerce=int, validators=[Optional()])
    submit = SubmitField("Назначить")
