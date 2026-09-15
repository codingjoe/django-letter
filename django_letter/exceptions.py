from __future__ import annotations

import typing

from django.core.exceptions import ImproperlyConfigured

if typing.TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser

    from .message import TemplateEmail

__all__ = [
    "EmailImproperlyConfigured",
    "InactiveUserError",
    "InvalidUserError",
    "MissingEmailError",
]


class EmailImproperlyConfigured(ImproperlyConfigured):
    """
    Signal that an email class misses what it needs to render.

    Catch it with Django's `ImproperlyConfigured`, which it derives from.
    """

    def __init__(self, email_class: type[TemplateEmail], message: str) -> None:
        self.email_class = email_class
        super().__init__(f"{email_class.__qualname__} {message}.")


class InvalidUserError(ValueError):
    """
    Signal that an account cannot receive a message.

    Catch it on its own to handle both failures at once.
    """

    message = "cannot receive this message"

    def __init__(self, user: AbstractUser) -> None:
        self.user = user
        super().__init__(f"{user} {self.message}.")


class InactiveUserError(InvalidUserError):
    """Signal that the account is deactivated."""

    message = "is inactive"


class MissingEmailError(InvalidUserError):
    """Signal that the account has no address to send to."""

    message = "has no email address"
