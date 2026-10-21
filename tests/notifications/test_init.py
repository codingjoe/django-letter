import hashlib

import pytest

from django_letter.notifications import (
    Notification,
    NotificationImproperlyConfigured,
    get_notification,
    get_notifications,
    hash_email,
)
from tests.testapp.emails import WeeklyDigestEmail, weekly_digest

EMAIL = "ada@example.com"


def test_hash_email__normalises_the_address() -> None:
    assert hash_email(" Ada@Example.COM ") == hash_email(EMAIL)


def test_hash_email__is_salted() -> None:
    assert hash_email(EMAIL) != hashlib.sha256(EMAIL.encode()).digest()


def test_hash_email__returns_a_32_byte_digest() -> None:
    assert len(hash_email(EMAIL)) == 32


def test_get_notification__returns_a_registered_notification() -> None:
    assert get_notification(weekly_digest.slug) is weekly_digest


def test_get_notification__returns_none_for_an_unknown_slug() -> None:
    assert get_notification("missing") is None


def test_get_notifications__keeps_registration_order() -> None:
    first = Notification("first", "First")
    second = Notification("second", "Second")
    assert get_notifications()[-2:] == (first, second)


def test_notification__decorator_attaches_itself() -> None:
    assert WeeklyDigestEmail.notification is weekly_digest


def test_notification__decorator_requires_the_subapp(monkeypatch) -> None:
    notification = Notification("decorated", "Decorated")
    monkeypatch.setattr(
        "django_letter.notifications.installed_apps.is_installed", lambda name: False
    )
    with pytest.raises(NotificationImproperlyConfigured, match="INSTALLED_APPS"):
        notification(type("Email", (), {}))


def test_notification__rejects_an_overlong_slug() -> None:
    with pytest.raises(
        NotificationImproperlyConfigured, match="is longer than 100 characters"
    ) as error:
        Notification("a" * 101, "Long")
    assert error.value.notification.slug == "a" * 101


@pytest.mark.parametrize("slug", ["", "Weekly Digest"])
def test_notification__rejects_an_invalid_slug(slug: str) -> None:
    with pytest.raises(
        NotificationImproperlyConfigured,
        match="is not a valid notification slug",
    ):
        Notification(slug, "Invalid")


def test_notification__rejects_a_duplicate_slug() -> None:
    with pytest.raises(
        NotificationImproperlyConfigured, match="is already registered"
    ) as error:
        Notification(weekly_digest.slug, "Again")
    assert error.value.notification is not weekly_digest
