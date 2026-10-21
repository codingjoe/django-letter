import pytest
from django.contrib.auth.models import User
from django.core.signing import b64_encode
from django.test import Client, RequestFactory
from django.urls import reverse

from django_letter.notifications import hash_email, signer
from django_letter.notifications.models import NotificationPreference
from django_letter.notifications.views import NotificationSettingsView
from tests.testapp.emails import weekly_digest

pytestmark = pytest.mark.django_db

EMAIL = "ada@example.com"
PREFERENCE = {"slug": weekly_digest.slug, "email_hash": hash_email(EMAIL)}


@pytest.fixture
def user() -> User:
    return User.objects.create_user("ada", email=EMAIL)


def settings_path() -> str:
    return reverse("django_letter_notifications:settings")


def unsubscribe_path(slug: str = weekly_digest.slug, token: str | None = None) -> str:
    return reverse(
        "django_letter_notifications:unsubscribe",
        kwargs={
            "token": token or signer.sign(b64_encode(hash_email(EMAIL)).decode()),
            "slug": slug,
        },
    )


def test_notification_settings_view__requires_login(client, settings) -> None:
    response = client.get(settings_path())
    assert response.status_code == 302
    assert settings.LOGIN_URL in response.url


def test_notification_settings_view__renders_the_user_form(client, user) -> None:
    client.force_login(user)
    response = client.get(settings_path())
    assert response.status_code == 200
    assert response.context["form"].email_hash == hash_email(EMAIL)
    assert "Weekly digest" in response.content.decode()


def test_notification_settings_view__saves_preferences(client, user) -> None:
    client.force_login(user)
    response = client.post(settings_path(), {weekly_digest.slug: "False"})
    assert response.status_code == 302
    assert response.url == settings_path()
    assert NotificationPreference.objects.get(**PREFERENCE).enabled is False


def test_notification_settings_view__uses_the_user_email_field() -> None:
    request = RequestFactory().get("/")
    request.user = type(
        "User", (), {"EMAIL_FIELD": "email_address", "email_address": EMAIL}
    )()
    view = NotificationSettingsView()
    view.request = request
    assert view.get_form_kwargs()["email"] == EMAIL


def test_notification_unsubscribe_view__get_disables_the_notification(client) -> None:
    response = client.get(unsubscribe_path())
    assert response.status_code == 302
    assert response.url == settings_path()
    assert NotificationPreference.objects.get(**PREFERENCE).enabled is False


def test_notification_unsubscribe_view__post_disables_the_notification(
    client,
) -> None:
    response = client.post(unsubscribe_path())
    assert response.status_code == 302
    assert response.url == settings_path()
    assert NotificationPreference.objects.get(**PREFERENCE).enabled is False


def test_notification_unsubscribe_view__post_needs_no_csrf_token() -> None:
    client = Client(enforce_csrf_checks=True)
    response = client.post(unsubscribe_path())
    assert response.status_code == 302


def test_notification_unsubscribe_view__handles_an_unknown_slug(client) -> None:
    response = client.get(unsubscribe_path("removed"))
    assert response.status_code == 302
    response = client.post(unsubscribe_path("removed"))
    assert response.status_code == 302
    assert not NotificationPreference.objects.exists()


def test_notification_unsubscribe_view__redirects_to_the_configured_url(
    client, settings
) -> None:
    settings.UNSUBSCRIBE_REDIRECT_URL = "/custom/settings/"
    response = client.get(unsubscribe_path())
    assert response.status_code == 302
    assert response.url == "/custom/settings/"


def test_notification_unsubscribe_view__redirects_to_the_settings_by_default(
    client,
) -> None:
    response = client.get(unsubscribe_path())
    assert response.status_code == 302
    assert response.url == settings_path()


def test_notification_unsubscribe_view__redirects_to_the_configured_route(
    client, settings
) -> None:
    settings.UNSUBSCRIBE_REDIRECT_URL = "django_letter:list"
    response = client.get(unsubscribe_path())
    assert response.status_code == 302
    assert response.url == reverse("django_letter:list")


def test_notification_unsubscribe_view__rejects_an_unsigned_token(client) -> None:
    response = client.get(unsubscribe_path(token="garbage"))
    assert response.status_code == 403


def test_notification_unsubscribe_view__rejects_a_token_without_a_digest(
    client,
) -> None:
    response = client.get(unsubscribe_path(token=signer.sign("")))
    assert response.status_code == 400


def test_notification_unsubscribe_view__rejects_a_token_with_a_short_digest(
    client,
) -> None:
    response = client.get(unsubscribe_path(token=signer.sign("ab")))
    assert response.status_code == 400


def test_notification_unsubscribe_view__rejects_a_token_that_is_not_base64(
    client,
) -> None:
    response = client.get(unsubscribe_path(token=signer.sign("a===")))
    assert response.status_code == 400
