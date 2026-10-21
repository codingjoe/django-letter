import hashlib
from dataclasses import dataclass

from django.apps import apps as installed_apps
from django.core.exceptions import ImproperlyConfigured
from django.core.signing import Signer
from django.utils.text import slugify

__all__ = [
    "Notification",
    "NotificationImproperlyConfigured",
    "NotificationRegistry",
    "hash_email",
    "registry",
    "signer",
]

signer = Signer(salt="django_letter.notifications")


class NotificationImproperlyConfigured(ImproperlyConfigured):
    """Signal that a notification is misconfigured."""

    def __init__(self, notification: Notification, message: str) -> None:
        self.notification = notification
        super().__init__(message)


def hash_email(email: str) -> bytes:
    return hashlib.sha256(
        f"django_letter.notifications{email.strip().lower()}".encode()
    ).digest()


@dataclass
class Notification:
    """
    Register one kind of email.

    The slug must be at most 100 characters and equal its own `slugify()`
    output. Use the instance as a class decorator to attach it to an email
    class.

    Raises:
        NotificationImproperlyConfigured: If the slug is too long, invalid, or
            already registered.
    """

    slug: str
    name: str
    help_text: str = ""
    default: bool = True

    def __post_init__(self) -> None:
        if len(self.slug) > 100:
            raise NotificationImproperlyConfigured(
                self, f"{self.slug!r} is longer than 100 characters."
            )
        if not self.slug or slugify(self.slug) != self.slug:
            raise NotificationImproperlyConfigured(
                self, f"{self.slug!r} is not a valid notification slug."
            )
        registry.register(self)

    def __call__(self, email_class: type) -> type:
        """Attach this notification to an email class."""
        if not installed_apps.is_installed("django_letter.notifications"):
            raise NotificationImproperlyConfigured(
                self,
                f"Notification {self.slug!r} requires"
                " 'django_letter.notifications' in INSTALLED_APPS.",
            )
        email_class.notification = self
        return email_class


class NotificationRegistry(dict[str, Notification]):
    """Store the registered notification kinds."""

    def register(self, notification: Notification) -> None:
        """Add a notification to the registry."""
        if notification.slug in self:
            raise NotificationImproperlyConfigured(
                notification,
                f"Notification {notification.slug!r} is already registered.",
            )
        self[notification.slug] = notification


registry = NotificationRegistry()
