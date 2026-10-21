import pytest
from django.core.signing import b64_encode
from django.urls import NoReverseMatch, reverse

from django_letter.exceptions import EmailImproperlyConfigured
from django_letter.message import _addresses
from django_letter.notifications import hash_email, signer
from django_letter.notifications.models import NotificationPreference
from tests.testapp.emails import WeeklyDigestEmail, WelcomeEmail, weekly_digest

pytestmark = pytest.mark.django_db

EMAIL = "ada@example.com"


class ContextTemplate:
    """Record the context that `render_html()` hands to the template."""

    def __init__(self) -> None:
        self.context: dict[str, object] = {}

    def render(self, context: dict[str, object]) -> str:
        self.context.update(context)
        return "<p>recorded</p>"


def test_get_unsubscribe_url__undecorated_email_returns_none() -> None:
    assert WelcomeEmail(language="en").get_unsubscribe_url() is None


def test_get_unsubscribe_url__decorated_without_recipient_returns_none() -> None:
    assert WeeklyDigestEmail(language="en", to=[]).get_unsubscribe_url() is None


@pytest.mark.parametrize(
    "recipients",
    [
        {"to": ["ada@example.com", "grace@example.com"]},
        {"to": ["ada@example.com"], "cc": ["grace@example.com"]},
        {"to": ["ada@example.com"], "bcc": ["grace@example.com"]},
    ],
)
def test_get_unsubscribe_url__requires_one_distinct_recipient(
    recipients: dict,
) -> None:
    email = WeeklyDigestEmail(language="en", **recipients)
    with pytest.raises(
        EmailImproperlyConfigured, match="cannot sign a link for multiple recipients"
    ):
        email.get_unsubscribe_url()


def test_get_unsubscribe_url__is_absolute_and_signed() -> None:
    email = WeeklyDigestEmail(language="en")
    url = email.get_unsubscribe_url()
    token = signer.sign(b64_encode(hash_email(EMAIL)).decode())
    assert url == (
        "http://testserver"
        + reverse(
            "django_letter_notifications:unsubscribe",
            kwargs={"token": token, "slug": weekly_digest.slug},
        )
    )


def test_get_unsubscribe_url__requires_the_mounted_urls(monkeypatch) -> None:
    def no_reverse(*args: object, **kwargs: object) -> str:
        raise NoReverseMatch

    monkeypatch.setattr("django_letter.message.reverse", no_reverse)
    with pytest.raises(NoReverseMatch):
        WeeklyDigestEmail(language="en").get_unsubscribe_url()


def test_get_unsubscribe_url__can_switch_recipients_before_rendering() -> None:
    email = WeeklyDigestEmail(language="en")
    first = email.get_unsubscribe_url()
    email.to = ["grace@example.com"]
    second = email.get_unsubscribe_url()
    assert first is not None
    assert second is not None
    assert first != second


def test_get_unsubscribe_url__one_address_in_any_case_is_one_recipient() -> None:
    url = WeeklyDigestEmail(
        language="en", to=["Ada@Example.COM"], cc=["ada@example.com"]
    ).get_unsubscribe_url()
    assert url is not None


def test_render__rejects_more_than_one_recipient() -> None:
    email = WeeklyDigestEmail(
        language="en", to=["ada@example.com", "grace@example.com"]
    )
    with pytest.raises(
        EmailImproperlyConfigured, match="cannot sign a link for multiple recipients"
    ):
        email.render()


def test_render_html__adds_the_notification_context(monkeypatch) -> None:
    template = ContextTemplate()
    monkeypatch.setattr(
        "django_letter.message.loader.get_template", lambda name: template
    )
    email = WeeklyDigestEmail(language="en")
    url = email.get_unsubscribe_url()
    assert url is not None
    email.render()
    assert template.context["notification"] is weekly_digest
    assert template.context["unsubscribe_url"] == url


def test_render_html__without_a_notification_omits_the_context(monkeypatch) -> None:
    template = ContextTemplate()
    monkeypatch.setattr(
        "django_letter.message.loader.get_template", lambda name: template
    )
    WelcomeEmail(language="en").render()
    assert "notification" not in template.context
    assert "unsubscribe_url" not in template.context


def test_render_html__without_a_recipient_omits_the_links(monkeypatch) -> None:
    template = ContextTemplate()
    monkeypatch.setattr(
        "django_letter.message.loader.get_template", lambda name: template
    )
    WeeklyDigestEmail(language="en", to=[]).render()
    assert template.context["notification"] is weekly_digest
    assert "unsubscribe_url" not in template.context


def test_message__adds_the_list_unsubscribe_headers() -> None:
    email = WeeklyDigestEmail(language="en")
    message = email.message()
    url = email.get_unsubscribe_url()
    assert url is not None
    assert message["List-Unsubscribe"] == f"<{url}>"
    assert message["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"


def test_message__keeps_the_sender_list_unsubscribe_headers() -> None:
    email = WeeklyDigestEmail(language="en")
    email.extra_headers["List-Unsubscribe"] = "<mailto:unsubscribe@example.com>"
    message = email.message()
    assert message["List-Unsubscribe"] == "<mailto:unsubscribe@example.com>"
    assert message["List-Unsubscribe-Post"] is None


def test_message__without_a_notification_has_no_list_unsubscribe_header() -> None:
    message = WelcomeEmail(language="en", to=[EMAIL]).message()
    assert message["List-Unsubscribe"] is None


def test_send__delivers_to_an_enabled_recipient(mailoutbox) -> None:
    email = WeeklyDigestEmail(language="en")
    assert email.send() == 1
    assert mailoutbox[0].to == [EMAIL]


def test_send__looks_up_preferences_once(django_assert_num_queries, mailoutbox) -> None:
    with django_assert_num_queries(1):
        WeeklyDigestEmail(language="en").send()
    assert len(mailoutbox) == 1


def test_send__keeps_the_display_name(mailoutbox) -> None:
    assert WeeklyDigestEmail(language="en", to=[f"Ada <{EMAIL}>"]).send() == 1
    assert mailoutbox[0].to == [f"Ada <{EMAIL}>"]


def test_send__skips_an_opted_out_recipient(mailoutbox) -> None:
    NotificationPreference.objects.set_enabled(weekly_digest, EMAIL, False)
    email = WeeklyDigestEmail(language="en", cc=[EMAIL])
    assert email.send() == 0
    assert mailoutbox == []
    assert email.to == [EMAIL]
    assert email.cc == [EMAIL]


def test_send__without_a_recipient_sends_nothing(mailoutbox) -> None:
    assert WeeklyDigestEmail(language="en", to=[]).send() == 0
    assert mailoutbox == []


def test_send__ignores_an_undecorated_email(mailoutbox) -> None:
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
def test_send__rejects_more_than_one_recipient(mailoutbox, recipients: dict) -> None:
    email = WeeklyDigestEmail(language="en", **recipients)
    with pytest.raises(
        EmailImproperlyConfigured, match="cannot sign a link for multiple recipients"
    ):
        email.send()
    assert mailoutbox == []


def test_addresses__reads_every_field_and_entry() -> None:
    assert _addresses("Ada <Ada@Example.COM>", ["grace@example.com", ""]) == [
        "ada@example.com",
        "grace@example.com",
    ]
