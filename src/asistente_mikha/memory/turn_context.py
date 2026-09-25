from __future__ import annotations

from contextvars import ContextVar, Token

# Mensaje del usuario del turno en curso. Las herramientas solo ven los
# argumentos que eligio el modelo; con esto pueden comprobar que lo que
# el modelo afirma que dijo el usuario, de verdad lo dijo. None significa
# "sin turno" (llamada directa, tests): no hay nada contra lo que comprobar.
_user_message: ContextVar[str | None] = ContextVar("mikha_user_message", default=None)


def set_user_message(message: str) -> Token:
    return _user_message.set(message)


def reset_user_message(token: Token) -> None:
    _user_message.reset(token)


def get_user_message() -> str | None:
    return _user_message.get()
