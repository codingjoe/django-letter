"""Public registry, signing, and preference API for notifications."""

import hashlib
import hmac
from collections.abc import Callable

from django.apps import apps
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.signing import Signer
from django.urls import reverse
from django.utils.text import slugify

__all__ = [
    "Notification",
    "NotificationImproperlyConfigured",
    "hash_email",
    "sign_email_hash",
    "subscribe",
    "unsign_email_hash",
]

SIGNING_SALT = "django_letter.notifications"

_registry: dict[str, Notification] = {}


class NotificationImproperlyConfigured(ImproperlyConfigured):
    """Signal that the registry or install is incomplete."""

    def __init__(self, notification: Notification, message: str) -> None:
        self.notification = notification
        super().__init__(message)


def hash_email(email: str) -> str:
    """
    Return the keyed SHA-256 digest of one address.

    The address is trimmed and lower-cased first, and the digest is 64
    lower-case hex characters. `SECRET_KEY` keys the digest, so a link holder
    cannot test guesses without it.
    """
    return hmac.new(
        settings.SECRET_KEY.encode(),
        email.strip().lower().encode(),
        hashlib.sha256,
    ).hexdigest()


def sign_email_hash(email_hash: str) -> str:
    """
    Return a token that proves the digest is unchanged.

    The token comes from Django's `Signer` with the
    `django_letter.notifications` salt. `unsign_email_hash()` reverses it.
    """
    return Signer(salt=SIGNING_SALT).sign(email_hash)


def unsign_email_hash(token: str) -> str:
    """
    Return the digest behind a token.

    Raise `BadSignature` when the token was altered or signed with another
    salt.
    """
    return Signer(salt=SIGNING_SALT).unsign(token)


class Notification:
    """
    Register a kind of email and track each recipient's preference.

    The slug names the kind in the URL, on the preferences form, and in
    storage. It must be 100 characters or fewer and must equal its own
    `slugify()` output. That allows lower-case ASCII letters, digits, hyphens,
    and underscores. Each slug registers once. A bad or duplicate slug raises
    `NotificationImproperlyConfigured`.
    """

    def __init__(
        self,
        slug: str,
        name: str,
        help_text: str = "",
        default: bool = True,
    ) -> None:
        self.slug = slug
        self.name = name
        self.help_text = help_text
        self.default = default
        if len(slug) > 100:
            raise NotificationImproperlyConfigured(
                self, f"{slug!r} is longer than 100 characters."
            )
        if not slug or slugify(slug) != slug:
            raise NotificationImproperlyConfigured(
                self, f"{slug!r} is not a valid notification slug."
            )
        if slug in _registry:
            raise NotificationImproperlyConfigured(
                self, f"Notification {slug!r} is already registered."
            )
        _registry[slug] = self

    @classmethod
    def find(cls, slug: str) -> Notification | None:
        """Return the notification registered under `slug`, if any."""
        return _registry.get(slug)

    @classmethod
    def get_all(cls) -> tuple[Notification, ...]:
        """Return every registered notification in registration order."""
        return tuple(_registry.values())

    def is_enabled(self, email: str) -> bool:
        """Return the stored override, or the default when none is stored."""
        self._check_app()
        from .models import NotificationPreference

        override = (
            NotificationPreference.objects.filter(
                email_hash=hash_email(email), slug=self.slug
            )
            .values_list("enabled", flat=True)
            .first()
        )
        return self.default if override is None else override

    def set_enabled(self, email: str, enabled: bool) -> None:
        """Turn the notification on or off for an address."""
        self.set_enabled_hash(hash_email(email), enabled)

    def set_enabled_hash(self, email_hash: str, enabled: bool) -> None:
        """Turn the notification on or off for one recipient."""
        self._check_app()
        from .models import NotificationPreference

        if enabled == self.default:
            NotificationPreference.objects.filter(
                email_hash=email_hash, slug=self.slug
            ).delete()
            return
        NotificationPreference.objects.update_or_create(
            email_hash=email_hash,
            slug=self.slug,
            defaults={"enabled": enabled},
        )

    def unsubscribe_url(self, base_url: str, email_hash: str) -> str:
        """
        Return the absolute link to the confirmation page for one digest.

        The page disables the notification only on POST, so a scanner that
        opens the link changes nothing.
        """
        return base_url.rstrip("/") + reverse(
            "django_letter_notifications:unsubscribe",
            kwargs={"token": sign_email_hash(email_hash), "slug": self.slug},
        )

    def manage_url(self, base_url: str, email_hash: str) -> str:
        """Return the absolute link to the preferences form for one digest."""
        return base_url.rstrip("/") + reverse(
            "django_letter_notifications:manage",
            kwargs={"token": sign_email_hash(email_hash)},
        )

    def _check_app(self) -> None:
        if not apps.is_installed("django_letter.notifications"):
            raise NotificationImproperlyConfigured(
                self,
                f"Notification {self.slug!r} requires"
                " 'django_letter.notifications' in INSTALLED_APPS.",
            )


def subscribe(notification: Notification) -> Callable[[type], type]:
    """Attach `notification` to an email class."""

    def decorate(email_class: type) -> type:
        email_class.notification = notification
        return email_class

    return decorate
