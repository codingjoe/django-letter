import pytest

from django_letter.fields import HashedEmailField
from django_letter.notifications.forms import NotificationForm
from django_letter.notifications.models import NotificationPreference
from tests.testapp.emails import weekly_digest

pytestmark = pytest.mark.django_db

EMAIL = "ada@example.com"
PREFERENCE = {
    "slug": weekly_digest.slug,
    "email_hash": HashedEmailField.hash_email(EMAIL),
}


def test_notification_form__hashes_an_address() -> None:
    form = NotificationForm(email=" Ada@Example.COM ")
    assert form.email_hash == HashedEmailField.hash_email(EMAIL)
    assert set(form.fields) == {weekly_digest.slug}
    assert form.fields[weekly_digest.slug].initial is True


def test_notification_form__reads_stored_overrides() -> None:
    NotificationPreference.objects.create(**PREFERENCE, enabled=False)
    form = NotificationForm(email=EMAIL)
    assert form.fields[weekly_digest.slug].initial is False


def test_notification_form__skips_the_preference_query_when_bound(
    django_assert_num_queries,
) -> None:
    NotificationPreference.objects.create(**PREFERENCE, enabled=False)
    with django_assert_num_queries(0):
        NotificationForm(email=EMAIL, data={weekly_digest.slug: False})


def test_notification_form__saves_the_submitted_choices() -> None:
    form = NotificationForm(email=EMAIL, data={weekly_digest.slug: False})
    form.full_clean()
    form.save()
    assert NotificationPreference.objects.get(**PREFERENCE).enabled is False


def test_notification_form__saves_with_one_query(django_assert_num_queries) -> None:
    form = NotificationForm(email=EMAIL, data={weekly_digest.slug: False})
    form.full_clean()
    with django_assert_num_queries(1):
        form.save()


def test_notification_form__saving_the_default_updates_the_override() -> None:
    preference = NotificationPreference.objects.create(**PREFERENCE, enabled=False)
    updated_at = preference.updated_at
    form = NotificationForm(email=EMAIL, data={weekly_digest.slug: True})
    form.full_clean()
    form.save()
    preference = NotificationPreference.objects.get(**PREFERENCE)
    assert preference.enabled is True
    assert preference.updated_at > updated_at
