from datetime import timedelta
from typing import Any, Callable, TypeVar

from flask import Flask

_F = TypeVar("_F", bound=Callable[..., Any])


class LoginManager:
    login_view: str | None
    login_message: str
    login_message_category: str

    def init_app(
        self,
        app: Flask,
        add_context_processor: bool = True,
    ) -> None: ...

    def user_loader(
        self,
        callback: Callable[[str], Any],
    ) -> Callable[[str], Any]: ...


def login_required(func: _F) -> _F: ...

# current_user — объект-прокси, а не функция.
# Any здесь используется на границе Flask-Login.
current_user: Any


def login_user(
    user: Any,
    remember: bool = False,
    duration: timedelta | None = None,
    force: bool = False,
    fresh: bool = True,
) -> bool: ...


def logout_user() -> None: ...