import pytest

from django_letter.notifications import hash_email
from django_letter.notifications.forms import NotificationForm
from django_letter.notifications.models import NotificationPreference
from tests.testapp.emails import weekly_digest

pytestmark = pytest.mark.django_db

EMAIL = "ada@example.com"
PREFERENCE = {"slug": weekly_digest.slug, "email_hash": hash_email(EMAIL)}


def test_notification_form__hashes_an_address() -> None:
    form = NotificationForm(email=" Ada@Example.COM ")
    assert form.email_hash == hash_email(EMAIL)
    assert set(form.fields) == {weekly_digest.slug}
    assert form.fields[weekly_digest.slug].initial is True


def test_notification_form__rejects_a_whitespace_only_address() -> None:
    with pytest.raises(ValueError, match="Pass a non-empty `email`."):
        NotificationForm(email="   ")


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


def test_notification_form__saving_the_default_removes_the_override() -> None:
    NotificationPreference.objects.create(**PREFERENCE, enabled=False)
    form = NotificationForm(email=EMAIL, data={weekly_digest.slug: True})
    form.full_clean()
    form.save()
    assert not NotificationPreference.objects.filter(**PREFERENCE).exists()
