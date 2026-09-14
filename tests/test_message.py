"""Behaviour of `TemplateEmail` outside the preview views."""

import re

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.utils import translation

from django_letter import TemplateEmail
from tests.testapp.emails import InvoiceEmail, WelcomeEmail


class UnnamedTemplateEmail(TemplateEmail):
    """An email that never names a template."""

    subject = "No template"


class UnnamedSubjectEmail(TemplateEmail):
    """An email that never names a subject."""

    template_name = "testapp/welcome.html"


class DeclaredLanguageEmail(TemplateEmail):
    """An email whose class-level language declaration must not apply."""

    language = "fr"


def test_get_context_data_defaults_to_empty() -> None:
    assert TemplateEmail(language="en").get_context_data() == {}


def test_slug() -> None:
    assert WelcomeEmail.slug() == "welcomeemail"


def test_get_email_classes() -> None:
    assert TemplateEmail.get_email_classes() == {
        "welcomeemail": WelcomeEmail,
        "invoiceemail": InvoiceEmail,
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
