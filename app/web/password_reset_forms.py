"""Forms used by customer password recovery."""

from flask_wtf import FlaskForm
from wtforms import PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo, Length


class ClientPasswordResetRequestForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=255)])
    submit = SubmitField("Отправить ссылку")


class ClientPasswordResetForm(FlaskForm):
    password = PasswordField("Новый пароль", validators=[DataRequired(), Length(min=12, max=128)])
    confirm_password = PasswordField(
        "Повторите пароль",
        validators=[DataRequired(), EqualTo("password", message="Пароли не совпадают.")],
    )
    submit = SubmitField("Сохранить пароль")
