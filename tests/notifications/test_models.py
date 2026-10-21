import pytest
from django.db import IntegrityError

from django_letter.notifications import Notification, hash_email
from django_letter.notifications.models import NotificationPreference
from tests.testapp.emails import weekly_digest

pytestmark = pytest.mark.django_db

EMAIL = "ada@example.com"
PREFERENCE = {"slug": weekly_digest.slug, "email_hash": hash_email(EMAIL)}


def test_notification_preference__str() -> None:
    preference = NotificationPreference(**PREFERENCE, enabled=False)
    assert str(preference) == f"weekly-digest for {hash_email(EMAIL).hex()}"


def test_notification_preference__is_unique_per_address_and_slug() -> None:
    NotificationPreference.objects.create(**PREFERENCE, enabled=False)
    with pytest.raises(IntegrityError):
        NotificationPreference.objects.create(**PREFERENCE, enabled=True)


def test_is_enabled__defaults_to_on() -> None:
    assert NotificationPreference.objects.is_enabled(weekly_digest, EMAIL) is True


def test_is_enabled__reads_the_override() -> None:
    NotificationPreference.objects.set_enabled_hash(
        weekly_digest, hash_email(EMAIL), False
    )
    assert NotificationPreference.objects.is_enabled(weekly_digest, EMAIL) is False


def test_is_enabled__honours_a_disabled_default() -> None:
    notification = Notification("opt-in", "Opt-in", default=False)
    assert NotificationPreference.objects.is_enabled(notification, EMAIL) is False
    NotificationPreference.objects.create(
        email_hash=hash_email(EMAIL), slug=notification.slug, enabled=True
    )
    assert NotificationPreference.objects.is_enabled(notification, EMAIL) is True


def test_set_enabled__hashes_the_address() -> None:
    NotificationPreference.objects.set_enabled(
        weekly_digest, " Ada@Example.COM ", False
    )
    assert NotificationPreference.objects.get(**PREFERENCE).enabled is False


def test_set_enabled_hash__stores_an_override_and_removes_the_default() -> None:
    digest = hash_email(EMAIL)
    NotificationPreference.objects.set_enabled_hash(weekly_digest, digest, False)
    preference = NotificationPreference.objects.get(**PREFERENCE)
    assert preference.enabled is False
    NotificationPreference.objects.set_enabled_hash(weekly_digest, digest, True)
    assert not NotificationPreference.objects.filter(**PREFERENCE).exists()
