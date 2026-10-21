"""Behaviour of the optional notification preferences and signed links."""

import re
from collections.abc import Iterator

import pytest
from django.core.signing import BadSignature
from django.db import IntegrityError
from django.test import Client
from django.urls import NoReverseMatch, reverse

from django_letter.exceptions import EmailImproperlyConfigured
from django_letter.message import NotificationLinks, _addresses, _recipient_list
from django_letter.notifications import (
    Notification,
    NotificationImproperlyConfigured,
    hash_email,
    sign_email_hash,
    unsign_email_hash,
)
from django_letter.notifications.api import _registry
from django_letter.notifications.forms import NotificationForm
from django_letter.notifications.models import NotificationPreference
from tests.testapp.emails import WEEKLY_DIGEST, WeeklyDigestEmail, WelcomeEmail

pytestmark = pytest.mark.django_db

EMAIL = "ada@example.com"
PREFERENCE = {"slug": WEEKLY_DIGEST.slug, "email_hash": hash_email(EMAIL)}


@pytest.fixture(autouse=True)
def restore_registry() -> Iterator[None]:
    """Return the global registry to its import-time state after each test."""
    before = dict(_registry)
    yield
    _registry.clear()
    _registry.update(before)


def manage_path(token: str | None = None) -> str:
    return reverse(
        "django_letter_notifications:manage",
        kwargs={"token": token or sign_email_hash(hash_email(EMAIL))},
    )


def unsubscribe_path(slug: str = WEEKLY_DIGEST.slug) -> str:
    return reverse(
        "django_letter_notifications:unsubscribe",
        kwargs={"token": sign_email_hash(hash_email(EMAIL)), "slug": slug},
    )


class ContextTemplate:
    """Record the context that `render_html()` hands to the template."""

    def __init__(self) -> None:
        self.context: dict[str, object] = {}

    def render(self, context: dict[str, object]) -> str:
        self.context.update(context)
        return "<p>recorded</p>"


# Keyed digest and signing


def test_hash_email_normalises_the_address() -> None:
    assert hash_email(" Ada@Example.COM ") == hash_email(EMAIL)


def test_hash_email_is_keyed(settings) -> None:
    digest = hash_email(EMAIL)
    settings.SECRET_KEY = "another-test-secret"
    assert hash_email(EMAIL) != digest


def test_hash_email_is_lowercase_hex() -> None:
    assert re.fullmatch(r"[0-9a-f]{64}", hash_email(EMAIL))


def test_sign_and_unsign_round_trip() -> None:
    digest = hash_email(EMAIL)
    assert unsign_email_hash(sign_email_hash(digest)) == digest


def test_unsign_rejects_a_tampered_token() -> None:
    with pytest.raises(BadSignature):
        unsign_email_hash(sign_email_hash(hash_email(EMAIL)) + "x")


# Registry


def test_find_returns_a_registered_notification() -> None:
    assert Notification.find(WEEKLY_DIGEST.slug) is WEEKLY_DIGEST


def test_find_returns_none_for_an_unknown_slug() -> None:
    assert Notification.find("missing") is None


def test_get_all_keeps_registration_order() -> None:
    first = Notification("first", "First")
    second = Notification("second", "Second")
    assert Notification.get_all()[-2:] == (first, second)


def test_subscribe_attaches_the_notification() -> None:
    assert WeeklyDigestEmail.notification is WEEKLY_DIGEST


def test_register_rejects_an_overlong_slug() -> None:
    with pytest.raises(
        NotificationImproperlyConfigured, match="is longer than 100 characters"
    ) as error:
        Notification("a" * 101, "Long")
    assert error.value.notification.slug == "a" * 101


@pytest.mark.parametrize("slug", ["", "Weekly Digest"])
def test_register_rejects_an_invalid_slug(slug: str) -> None:
    with pytest.raises(
        NotificationImproperlyConfigured,
        match="is not a valid notification slug",
    ):
        Notification(slug, "Invalid")


def test_register_rejects_a_duplicate_slug() -> None:
    with pytest.raises(
        NotificationImproperlyConfigured, match="is already registered"
    ) as error:
        Notification(WEEKLY_DIGEST.slug, "Again")
    assert error.value.notification is not WEEKLY_DIGEST


# Preferences


def test_is_enabled_defaults_to_on() -> None:
    assert WEEKLY_DIGEST.is_enabled(EMAIL) is True


def test_is_enabled_reads_the_override() -> None:
    WEEKLY_DIGEST.set_enabled_hash(hash_email(EMAIL), False)
    assert WEEKLY_DIGEST.is_enabled(EMAIL) is False


def test_is_enabled_honours_a_disabled_default() -> None:
    notification = Notification("opt-in", "Opt-in", default=False)
    assert notification.is_enabled(EMAIL) is False
    NotificationPreference.objects.create(
        email_hash=hash_email(EMAIL), slug=notification.slug, enabled=True
    )
    assert notification.is_enabled(EMAIL) is True


def test_set_enabled_hashes_the_address() -> None:
    WEEKLY_DIGEST.set_enabled(" Ada@Example.COM ", False)
    assert NotificationPreference.objects.get(**PREFERENCE).enabled is False


def test_set_enabled_hash_stores_an_override_and_removes_the_default() -> None:
    digest = hash_email(EMAIL)
    WEEKLY_DIGEST.set_enabled_hash(digest, False)
    preference = NotificationPreference.objects.get(**PREFERENCE)
    assert preference.enabled is False
    WEEKLY_DIGEST.set_enabled_hash(digest, True)
    assert not NotificationPreference.objects.filter(**PREFERENCE).exists()


def test_preferences_require_the_subapp(monkeypatch) -> None:
    monkeypatch.setattr(
        "django_letter.notifications.api.apps.is_installed", lambda name: False
    )
    message = re.escape(
        "Notification 'weekly-digest' requires 'django_letter.notifications'"
        " in INSTALLED_APPS."
    )
    with pytest.raises(NotificationImproperlyConfigured, match=message):
        WEEKLY_DIGEST.is_enabled(EMAIL)
    with pytest.raises(NotificationImproperlyConfigured, match=message):
        WEEKLY_DIGEST.set_enabled_hash(hash_email(EMAIL), False)


def test_notification_links_are_absolute_and_signed() -> None:
    links = WeeklyDigestEmail(language="en").get_notification_urls()
    assert isinstance(links, NotificationLinks)
    token = sign_email_hash(hash_email(EMAIL))
    assert links.unsubscribe == (
        "http://testserver"
        + reverse(
            "django_letter_notifications:unsubscribe",
            kwargs={"token": token, "slug": WEEKLY_DIGEST.slug},
        )
    )
    assert links.manage == (
        "http://testserver"
        + reverse(
            "django_letter_notifications:manage",
            kwargs={"token": token},
        )
    )


# Model


def test_preference_str() -> None:
    preference = NotificationPreference(**PREFERENCE, enabled=False)
    assert str(preference) == f"weekly-digest for {hash_email(EMAIL)}"


def test_preference_is_unique_per_address_and_slug() -> None:
    NotificationPreference.objects.create(**PREFERENCE, enabled=False)
    with pytest.raises(IntegrityError):
        NotificationPreference.objects.create(**PREFERENCE, enabled=True)


# Form


def test_form_hashes_an_address() -> None:
    form = NotificationForm(email=" Ada@Example.COM ")
    assert form.email_hash == hash_email(EMAIL)
    assert set(form.fields) == {WEEKLY_DIGEST.slug}
    assert form.fields[WEEKLY_DIGEST.slug].initial is True


def test_form_accepts_a_digest() -> None:
    assert NotificationForm(email_hash=hash_email(EMAIL)).email_hash == hash_email(
        EMAIL
    )


def test_form_rejects_an_address_and_a_digest_together() -> None:
    with pytest.raises(ValueError, match="Pass only one of `email` or `email_hash`."):
        NotificationForm(email=EMAIL, email_hash=hash_email(EMAIL))


def test_form_requires_an_address_or_a_digest() -> None:
    with pytest.raises(ValueError, match="Pass `email` or `email_hash`."):
        NotificationForm()


@pytest.mark.parametrize("email_hash", ["abc", "A" * 64, "g" * 64])
def test_form_rejects_a_malformed_digest(email_hash: str) -> None:
    with pytest.raises(ValueError, match="64 lowercase hex characters"):
        NotificationForm(email_hash=email_hash)


def test_form_rejects_a_whitespace_only_address() -> None:
    with pytest.raises(ValueError, match="Pass `email` or `email_hash`."):
        NotificationForm(email="   ")


def test_form_reads_stored_overrides() -> None:
    NotificationPreference.objects.create(**PREFERENCE, enabled=False)
    form = NotificationForm(email_hash=hash_email(EMAIL))
    assert form.fields[WEEKLY_DIGEST.slug].initial is False


def test_bound_form_skips_the_preference_query(django_assert_num_queries) -> None:
    NotificationPreference.objects.create(**PREFERENCE, enabled=False)
    with django_assert_num_queries(0):
        NotificationForm(email_hash=hash_email(EMAIL), data={WEEKLY_DIGEST.slug: False})


def test_form_saves_the_submitted_choices() -> None:
    form = NotificationForm(
        email_hash=hash_email(EMAIL), data={WEEKLY_DIGEST.slug: False}
    )
    form.full_clean()
    form.save()
    assert NotificationPreference.objects.get(**PREFERENCE).enabled is False


def test_form_saving_the_default_removes_the_override() -> None:
    NotificationPreference.objects.create(**PREFERENCE, enabled=False)
    form = NotificationForm(
        email_hash=hash_email(EMAIL), data={WEEKLY_DIGEST.slug: True}
    )
    form.full_clean()
    form.save()
    assert not NotificationPreference.objects.filter(**PREFERENCE).exists()


# Views


def test_manage_page_lists_every_notification(client) -> None:
    response = client.get(manage_path())
    assert response.status_code == 200
    assert response.context["form"].email_hash == hash_email(EMAIL)
    assert "Weekly digest" in response.content.decode()
    assert "Your preferences were saved." not in response.content.decode()


def test_manage_page_confirms_a_save(client) -> None:
    response = client.get(manage_path(), {"saved": 1})
    assert "Your preferences were saved." in response.content.decode()


def test_manage_page_reports_an_empty_registry(client) -> None:
    _registry.clear()
    response = client.get(manage_path())
    assert response.status_code == 200
    assert "There are no notifications to configure." in response.content.decode()


def test_manage_post_saves_and_redirects(client) -> None:
    response = client.post(manage_path(), {WEEKLY_DIGEST.slug: "False"})
    assert response.status_code == 302
    assert response.url == f"{manage_path()}?saved=1"
    assert NotificationPreference.objects.get(**PREFERENCE).enabled is False


def test_manage_rejects_an_unsigned_token(client) -> None:
    response = client.get(manage_path("garbage"))
    assert response.status_code == 404


def test_manage_rejects_a_token_without_a_digest(client) -> None:
    response = client.get(manage_path(sign_email_hash("not-a-digest")))
    assert response.status_code == 404


def test_unsubscribe_page_asks_for_confirmation(client) -> None:
    response = client.get(unsubscribe_path())
    assert response.status_code == 200
    assert "Weekly digest" in response.content.decode()
    assert not NotificationPreference.objects.exists()


def test_unsubscribe_post_disables_the_notification(client) -> None:
    response = client.post(unsubscribe_path())
    assert response.status_code == 200
    assert "You will no longer receive" in response.content.decode()
    assert NotificationPreference.objects.get(**PREFERENCE).enabled is False


def test_unsubscribe_post_needs_no_csrf_token() -> None:
    client = Client(enforce_csrf_checks=True)
    response = client.post(unsubscribe_path())
    assert response.status_code == 200


def test_unsubscribe_handles_an_unknown_slug(client) -> None:
    response = client.get(unsubscribe_path("removed"))
    assert response.status_code == 200
    assert "removed" in response.content.decode()
    response = client.post(unsubscribe_path("removed"))
    assert response.status_code == 200
    assert not NotificationPreference.objects.exists()


# Message links, headers, and sending


def test_undecorated_email_has_no_notification_urls() -> None:
    assert WelcomeEmail(language="en").get_notification_urls() is None


def test_decorated_email_without_a_recipient_has_no_urls() -> None:
    assert WeeklyDigestEmail(language="en", to=[]).get_notification_urls() is None


@pytest.mark.parametrize(
    "recipients",
    [
        {"to": ["ada@example.com", "grace@example.com"]},
        {"to": ["ada@example.com"], "cc": ["grace@example.com"]},
        {"to": ["ada@example.com"], "bcc": ["grace@example.com"]},
    ],
)
def test_links_require_one_distinct_recipient(recipients: dict) -> None:
    email = WeeklyDigestEmail(language="en", **recipients)
    with pytest.raises(
        EmailImproperlyConfigured, match="cannot sign a link for multiple recipients"
    ):
        email.get_notification_urls()


def test_render_rejects_more_than_one_recipient() -> None:
    email = WeeklyDigestEmail(
        language="en", to=["ada@example.com", "grace@example.com"]
    )
    with pytest.raises(
        EmailImproperlyConfigured, match="cannot sign a link for multiple recipients"
    ):
        email.render()


def test_links_require_the_mounted_urls(monkeypatch) -> None:
    def no_reverse(*args: object, **kwargs: object) -> str:
        raise NoReverseMatch

    monkeypatch.setattr("django_letter.notifications.api.reverse", no_reverse)
    with pytest.raises(
        EmailImproperlyConfigured,
        match=re.escape(
            "WeeklyDigestEmail cannot build notification links."
            " Mount 'django_letter.notifications.urls'."
        ),
    ):
        WeeklyDigestEmail(language="en").get_notification_urls()


def test_recipient_list_wraps_one_entry() -> None:
    assert _recipient_list(EMAIL) == [EMAIL]
    assert _recipient_list([EMAIL]) == [EMAIL]


def test_addresses_reads_every_field_and_entry() -> None:
    assert _addresses("Ada <Ada@Example.COM>", ["grace@example.com", ""]) == [
        "ada@example.com",
        "grace@example.com",
    ]


def test_one_address_in_any_case_is_one_recipient() -> None:
    links = WeeklyDigestEmail(
        language="en", to=["Ada@Example.COM"], cc=["ada@example.com"]
    ).get_notification_urls()
    assert links is not None


def test_links_can_switch_recipients_before_rendering() -> None:
    email = WeeklyDigestEmail(language="en")
    first = email.get_notification_urls()
    email.to = ["grace@example.com"]
    second = email.get_notification_urls()
    assert first is not None
    assert second is not None
    assert first.unsubscribe != second.unsubscribe


def test_rendered_message_cannot_switch_recipients() -> None:
    email = WeeklyDigestEmail(language="en")
    email.render()
    email.to = ["grace@example.com"]
    with pytest.raises(
        EmailImproperlyConfigured,
        match="cannot reuse a rendered message for another recipient",
    ):
        email.get_notification_urls()


def test_render_html_adds_the_notification_context(monkeypatch) -> None:
    template = ContextTemplate()
    monkeypatch.setattr(
        "django_letter.message.loader.get_template", lambda name: template
    )
    email = WeeklyDigestEmail(language="en")
    links = email.get_notification_urls()
    assert links is not None
    email.render()
    assert template.context["notification"] is WEEKLY_DIGEST
    assert template.context["unsubscribe_url"] == links.unsubscribe
    assert template.context["manage_notifications_url"] == links.manage


def test_render_html_without_a_notification_omits_the_context(monkeypatch) -> None:
    template = ContextTemplate()
    monkeypatch.setattr(
        "django_letter.message.loader.get_template", lambda name: template
    )
    WelcomeEmail(language="en").render()
    assert "notification" not in template.context
    assert "unsubscribe_url" not in template.context
    assert "manage_notifications_url" not in template.context


def test_render_html_without_a_recipient_omits_the_links(monkeypatch) -> None:
    template = ContextTemplate()
    monkeypatch.setattr(
        "django_letter.message.loader.get_template", lambda name: template
    )
    WeeklyDigestEmail(language="en", to=[]).render()
    assert template.context["notification"] is WEEKLY_DIGEST
    assert "unsubscribe_url" not in template.context


def test_message_adds_the_list_unsubscribe_headers() -> None:
    email = WeeklyDigestEmail(language="en")
    message = email.message()
    links = email.get_notification_urls()
    assert links is not None
    assert message["List-Unsubscribe"] == f"<{links.unsubscribe}>"
    assert message["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"


def test_message_keeps_the_sender_list_unsubscribe_headers() -> None:
    email = WeeklyDigestEmail(language="en")
    email.extra_headers["List-Unsubscribe"] = "<mailto:unsubscribe@example.com>"
    message = email.message()
    assert message["List-Unsubscribe"] == "<mailto:unsubscribe@example.com>"
    assert message["List-Unsubscribe-Post"] is None


def test_message_without_a_notification_has_no_list_unsubscribe_header() -> None:
    message = WelcomeEmail(language="en", to=[EMAIL]).message()
    assert message["List-Unsubscribe"] is None


def test_send_delivers_to_an_enabled_recipient(mailoutbox) -> None:
    email = WeeklyDigestEmail(language="en")
    assert email.send() == 1
    assert mailoutbox[0].to == [EMAIL]


def test_send_looks_up_preferences_once(django_assert_num_queries, mailoutbox) -> None:
    with django_assert_num_queries(1):
        WeeklyDigestEmail(language="en").send()
    assert len(mailoutbox) == 1


def test_send_keeps_the_display_name(mailoutbox) -> None:
    assert WeeklyDigestEmail(language="en", to=[f"Ada <{EMAIL}>"]).send() == 1
    assert mailoutbox[0].to == [f"Ada <{EMAIL}>"]


def test_send_skips_an_opted_out_recipient(mailoutbox) -> None:
    WEEKLY_DIGEST.set_enabled(EMAIL, False)
    email = WeeklyDigestEmail(language="en", cc=[EMAIL])
    assert email.send() == 0
    assert mailoutbox == []
    assert email.to == [EMAIL]
    assert email.cc == [EMAIL]


def test_send_without_a_recipient_sends_nothing(mailoutbox) -> None:
    assert WeeklyDigestEmail(language="en", to=[]).send() == 0
    assert mailoutbox == []


def test_send_ignores_an_undecorated_email(mailoutbox) -> None:
    assert WelcomeEmail(language="en", to=[EMAIL]).send() == 1
    assert len(mailoutbox) == 1


@pytest.mark.parametrize(
    "recipients",
    [
        {"to": ["ada@example.com", "grace@example.com"]},
        {"to": ["ada@example.com"], "cc": ["grace@example.com"]},
        {"to": ["ada@example.com"], "bcc": ["grace@example.com"]},
    ],
)
def test_send_rejects_more_than_one_recipient(mailoutbox, recipients: dict) -> None:
    email = WeeklyDigestEmail(language="en", **recipients)
    with pytest.raises(
        EmailImproperlyConfigured, match="cannot sign a link for multiple recipients"
    ):
        email.send()
    assert mailoutbox == []
