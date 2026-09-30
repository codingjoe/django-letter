"""Behaviour of `TemplateEmail` outside the preview views."""

import re
from email.message import Message, MIMEPart
from pathlib import Path

import django
import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ImproperlyConfigured
from django.utils import translation

from django_letter import TemplateEmail
from django_letter.exceptions import (
    EmailImproperlyConfigured,
    InactiveUserError,
    InvalidUserError,
    MissingEmailError,
)
from django_letter.message import StaticImage, _attached_static_part
from tests.testapp.emails import (
    InvoiceEmail,
    LogoEmail,
    RemoteImagesEmail,
    RetinaLogoEmail,
    WelcomeEmail,
)

STATIC_DIR = Path(__file__).parent / "testapp" / "static" / "testapp"
LOGO = STATIC_DIR / "logo.png"
LOGO_2X = STATIC_DIR / "logo.png@2x.png"
LOGO_UNKNOWN = STATIC_DIR / "logo.unknown"


@pytest.fixture
def user() -> User:
    return User(
        username="ada",
        first_name="Ada",
        last_name="Lovelace",
        email="ada@example.com",
    )


class UnnamedTemplateEmail(TemplateEmail):
    """An email that never names a template."""

    subject = "No template"


class UnnamedSubjectEmail(TemplateEmail):
    """An email that never names a subject."""

    template_name = "testapp/welcome.html"


class DeclaredLanguageEmail(TemplateEmail):
    """An email whose class-level language declaration must not apply."""

    language = "fr"


class GreetingEmail(TemplateEmail):
    """An email that keeps the default context to greet its user."""

    template_name = "testapp/welcome.html"

    def get_context_data(self) -> dict[str, object]:
        return super().get_context_data() | {"name": "Ada"}


def inline_part(message: Message, content_id: str) -> Message:
    """Return the part that carries the inline picture `content_id`."""
    return next(
        part for part in message.walk() if part["Content-ID"] == f"<{content_id}>"
    )


def assert_inline_image(part: Message, content: bytes) -> None:
    """Assert that `part` is the inline PNG picture `content`."""
    assert part.get_content_type() == "image/png"
    assert part["Content-Transfer-Encoding"] == "base64"
    assert part["Content-Disposition"] == "inline"
    assert part.get_payload(decode=True) == content


def test_get_context_data_defaults_to_empty() -> None:
    assert TemplateEmail(language="en").get_context_data() == {}


def test_extra_context_joins_the_context() -> None:
    email = GreetingEmail(language="en", extra_context={"greeting": "Hello"})
    assert email.get_context_data() == {"greeting": "Hello", "name": "Ada"}


def test_get_context_data_returns_a_copy() -> None:
    email = TemplateEmail(language="en", extra_context={"greeting": "Hello"})
    email.get_context_data()["greeting"] = "Hi"
    assert email.get_context_data() == {"greeting": "Hello"}


def test_slug() -> None:
    assert WelcomeEmail.slug() == "welcomeemail"


def test_get_email_classes() -> None:
    assert TemplateEmail.get_email_classes() == {
        "welcomeemail": WelcomeEmail,
        "invoiceemail": InvoiceEmail,
        "logoemail": LogoEmail,
        "retinalogoemail": RetinaLogoEmail,
        "remoteimagesemail": RemoteImagesEmail,
    }


def test_missing_template() -> None:
    with pytest.raises(
        ImproperlyConfigured, match="UnnamedTemplateEmail is missing a template."
    ):
        UnnamedTemplateEmail(language="en").get_template()


def test_missing_subject() -> None:
    with pytest.raises(
        ImproperlyConfigured, match="UnnamedSubjectEmail is missing a subject."
    ):
        UnnamedSubjectEmail(language="en").get_subject()


def test_language_from_argument() -> None:
    assert WelcomeEmail(language="de").language == "de"


def test_class_language_declaration_is_ignored() -> None:
    with pytest.raises(
        ImproperlyConfigured, match="DeclaredLanguageEmail is missing a language."
    ):
        DeclaredLanguageEmail()
    assert DeclaredLanguageEmail(language="de").language == "de"


def test_missing_language() -> None:
    with pytest.raises(
        ImproperlyConfigured, match="TemplateEmail is missing a language."
    ):
        TemplateEmail()
    with pytest.raises(
        ImproperlyConfigured, match="WelcomeEmail is missing a language."
    ):
        WelcomeEmail(to=["ada@example.com"])


def test_language_falls_back_when_i18n_is_off(settings) -> None:
    # Django dispatches translation calls lazily and caches the backend it
    # resolves; resolve it while i18n is on so the disabled setting cannot leak
    # into later tests.
    translation.get_language()
    settings.USE_I18N = False
    assert TemplateEmail().language == "en-us"


def test_render() -> None:
    email = WelcomeEmail(name="Ada", language="en")
    email.render()
    html, mimetype = email.alternatives[0]
    assert mimetype == "text/html"
    assert "background-color:#0867ec" in html  # inlined by premailer
    assert 'href="http://testserver/welcome/confirm"' in html  # from ALLOWED_HOSTS
    assert email.subject == "Welcome, Ada"
    assert email.body.startswith("Your account is ready, Ada.")
    assert "Confirm address <http://testserver/welcome/confirm>" in email.body
    assert "Remind me later" in email.body


def test_render_merges_extra_context() -> None:
    email = WelcomeEmail(name="Ada", language="en")
    email.render(name="Grace")
    assert email.subject == "Welcome, Grace"
    assert "Welcome, Grace" in email.html
    assert email.body.startswith("Your account is ready, Grace.")


def test_render_ignores_context_after_the_first_call() -> None:
    email = WelcomeEmail(name="Ada", language="en")
    email.render(name="Grace")
    email.render(name="Heidi")
    assert "Welcome, Grace" in email.html
    assert len(email.alternatives) == 1


def test_render_attachments() -> None:
    email = InvoiceEmail(language="en")
    email.render()
    assert email.attachments == [
        ("terms.txt", "Payment is due within 30 days.", "text/plain"),
        ("logo.png", b"\x89PNG\r\n", "image/png"),
    ]


def test_message_renders_once() -> None:
    email = InvoiceEmail(language="en")
    email.message()
    email.message()
    assert len(email.alternatives) == 1
    assert len(email.attachments) == 2


def test_attach_static_registers_the_picture() -> None:
    email = LogoEmail(language="en")
    assert email.attach_static("testapp/logo.png") == "cid:logo.png"
    assert email.attach_static("testapp/logo.png") == "cid:logo.png"
    assert email.attached_static == {
        "logo.png": StaticImage(path=LOGO, url="/static/testapp/logo.png")
    }


def test_attach_static_rejects_two_files_with_one_name() -> None:
    email = LogoEmail(language="en")
    email.attach_static("testapp/logo.png")
    with pytest.raises(
        EmailImproperlyConfigured,
        match="LogoEmail cannot attach two static files named logo.png.",
    ):
        email.attach_static("testapp/nested/logo.png")


def test_attach_static_rejects_a_name_no_finder_resolves() -> None:
    with pytest.raises(
        EmailImproperlyConfigured,
        match="LogoEmail cannot find the static file testapp/missing.png.",
    ):
        LogoEmail(language="en").attach_static("testapp/missing.png")


def test_attach_static_rejects_a_directory() -> None:
    """A finder happily resolves the static directory of an app itself."""
    with pytest.raises(
        EmailImproperlyConfigured,
        match="LogoEmail cannot find the static file testapp.",
    ):
        LogoEmail(language="en").attach_static("testapp")


def test_attached_static_part_without_a_known_extension() -> None:
    """A name that `mimetypes` cannot place travels as a plain binary."""
    part = _attached_static_part(LOGO_UNKNOWN, "logo.unknown")
    assert part.get_content_type() == "application/octet-stream"
    assert part.get_payload(decode=True) == LOGO_UNKNOWN.read_bytes()


def test_render_attaches_the_picture_inline() -> None:
    email = LogoEmail(language="en")
    email.render()
    assert 'src="cid:logo.png"' in email.html
    assert_inline_image(inline_part(email.message(), "logo.png"), LOGO.read_bytes())


def test_render_attaches_the_picture_in_both_densities() -> None:
    email = RetinaLogoEmail(language="en")
    email.render()
    assert 'src="cid:logo.png"' in email.html
    assert 'src="cid:logo.png@2x.png"' in email.html
    message = email.message()
    assert_inline_image(inline_part(message, "logo.png"), LOGO.read_bytes())
    assert_inline_image(inline_part(message, "logo.png@2x.png"), LOGO_2X.read_bytes())


def test_attached_static_part_on_django_before_6(monkeypatch) -> None:
    """
    Django 5.2 builds the part from `MIMEBase`.

    It shares the content type, base64 encoding, inline disposition and content
    ID with the modern shape, and also carries `MIME-Version`.
    """
    monkeypatch.setattr(django, "VERSION", (5, 2, 0, "final", 0))
    part = _attached_static_part(LOGO, "logo.png")
    assert not isinstance(part, MIMEPart)
    assert part["Content-ID"] == "<logo.png>"
    assert_inline_image(part, LOGO.read_bytes())


def test_render_preview_returns_rendered_email() -> None:
    email = WelcomeEmail.render_preview(language="en")
    assert isinstance(email, WelcomeEmail)
    assert email.language == "en"
    assert email.subject == "Welcome, Ada"
    assert "Welcome, Ada" in email.html
    assert email.body.startswith("Your account is ready, Ada.")


def test_render_preview_uses_the_active_language(rf) -> None:
    email = WelcomeEmail.render_preview(rf.get("/"))
    assert email.language == "en-us"
    assert '<html lang="en-us">' in email.html


def test_render_preview_merges_context() -> None:
    email = WelcomeEmail.render_preview(context={"name": "Grace"}, language="de")
    assert email.subject == "Welcome, Grace"
    assert "Welcome, Grace" in email.html
    assert '<html lang="de">' in email.html
    assert email.body.startswith("Your account is ready, Grace.")


def test_missing_base_url(settings) -> None:
    settings.ALLOWED_HOSTS = []
    message = re.escape(
        "WelcomeEmail cannot build a base URL."
        " Set `base_url` or add a host to ALLOWED_HOSTS."
    )
    with pytest.raises(ImproperlyConfigured, match=message):
        WelcomeEmail(language="en").get_base_url()
    with pytest.raises(ImproperlyConfigured, match=message):
        WelcomeEmail.render_preview()


def test_base_url_from_allowed_hosts(settings) -> None:
    settings.ALLOWED_HOSTS = ["example.com"]
    assert WelcomeEmail(language="en").get_base_url() == "http://example.com"
    html = WelcomeEmail.render_preview().html
    assert 'href="http://example.com/welcome/confirm"' in html

    settings.ALLOWED_HOSTS = ["", "*", ".example.com"]
    # The empty entry and "*" are skipped and the leading dot is stripped.
    assert WelcomeEmail(language="en").get_base_url() == "http://example.com"


def test_base_url_secured(settings) -> None:
    settings.ALLOWED_HOSTS = ["example.com"]
    settings.SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    assert WelcomeEmail(language="en").get_base_url() == "https://example.com"

    settings.SECURE_PROXY_SSL_HEADER = None
    settings.SECURE_HSTS_SECONDS = 31_536_000
    assert WelcomeEmail(language="en").get_base_url() == "https://example.com"


def test_base_url_attribute_wins(settings, monkeypatch) -> None:
    settings.ALLOWED_HOSTS = ["example.com"]
    monkeypatch.setattr(WelcomeEmail, "base_url", "https://attribute.example.com")
    assert WelcomeEmail(language="en").get_base_url() == "https://attribute.example.com"


def test_sender_arguments_reach_the_message() -> None:
    email = WelcomeEmail(
        name="Ada",
        language="en",
        to=["ada@example.com"],
        cc=["grace@example.com"],
        reply_to=["ada@example.com"],
    )
    assert email.to == ["ada@example.com"]
    assert email.cc == ["grace@example.com"]
    assert email.reply_to == ["ada@example.com"]


def test_base_url_argument_wins(settings) -> None:
    settings.ALLOWED_HOSTS = ["example.com"]
    email = WelcomeEmail(language="en", base_url="https://argument.example.com")
    assert email.get_base_url() == "https://argument.example.com"
    email.render()
    assert "https://argument.example.com/welcome/confirm" in email.html


def test_to_user(user) -> None:
    assert WelcomeEmail.to_user(user, language="en").to == [
        "Ada Lovelace <ada@example.com>"
    ]


def test_to_user_joins_the_context(user) -> None:
    assert GreetingEmail.to_user(user, language="en").get_context_data() == {
        "user": user,
        "name": "Ada",
    }


def test_to_user_without_a_full_name(user) -> None:
    user.first_name = ""
    user.last_name = ""
    assert WelcomeEmail.to_user(user, language="en").to == ["ada@example.com"]


def test_to_user_passes_arguments_through(user) -> None:
    email = WelcomeEmail.to_user(user, language="en", cc=["heidi@example.com"])
    assert email.cc == ["heidi@example.com"]


def test_to_user_addresses_the_message(user, settings) -> None:
    settings.ALLOWED_HOSTS = ["example.com"]
    message = WelcomeEmail.to_user(user, language="en").message()
    assert message["To"] == "Ada Lovelace <ada@example.com>"
    assert message["Subject"] == "Welcome, Ada"


def test_to_user_without_email(user) -> None:
    user.email = ""
    with pytest.raises(MissingEmailError, match="ada has no email address."):
        WelcomeEmail.to_user(user, language="en")


def test_to_user_inactive(user) -> None:
    user.is_active = False
    with pytest.raises(InactiveUserError, match="ada is inactive."):
        WelcomeEmail.to_user(user, language="en")


def test_invalid_user_errors_are_value_errors() -> None:
    assert issubclass(InactiveUserError, InvalidUserError)
    assert issubclass(MissingEmailError, InvalidUserError)
    assert issubclass(InvalidUserError, ValueError)


def test_email_improperly_configured_renders_the_class() -> None:
    error = EmailImproperlyConfigured(WelcomeEmail, "is missing a subject")
    assert error.email_class is WelcomeEmail
    assert str(error) == "WelcomeEmail is missing a subject."
    assert isinstance(error, ImproperlyConfigured)


def test_invalid_user_errors_render_the_user(user) -> None:
    inactive = InactiveUserError(user)
    assert inactive.user is user
    assert str(inactive) == "ada is inactive."

    missing = MissingEmailError(user)
    assert missing.user is user
    assert str(missing) == "ada has no email address."
