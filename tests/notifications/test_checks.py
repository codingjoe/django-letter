from django.template import TemplateDoesNotExist, TemplateSyntaxError
from django.urls import NoReverseMatch

from django_letter.notifications.checks import (
    check_settings_template,
    check_unsubscribe_url,
)


def test_check_unsubscribe_url__passes_when_the_urls_are_mounted() -> None:
    assert check_unsubscribe_url() == []


def test_check_unsubscribe_url__reports_missing_urls(monkeypatch) -> None:
    def no_reverse(*args: object, **kwargs: object) -> str:
        raise NoReverseMatch

    monkeypatch.setattr("django_letter.notifications.checks.reverse", no_reverse)
    errors = check_unsubscribe_url()
    assert len(errors) == 1
    assert errors[0].id == "django_letter.notifications.E001"


def test_check_settings_template__passes_when_the_template_exists() -> None:
    assert check_settings_template() == []


def test_check_settings_template__reports_a_missing_template(monkeypatch) -> None:
    def no_template(name: str) -> None:
        raise TemplateDoesNotExist(name)

    monkeypatch.setattr("django_letter.notifications.checks.get_template", no_template)
    errors = check_settings_template()
    assert len(errors) == 1
    assert errors[0].id == "django_letter.notifications.E002"


def test_check_settings_template__reports_a_syntax_error(monkeypatch) -> None:
    def broken_template(name: str) -> None:
        raise TemplateSyntaxError("bad tag")  # noqa: TRY003

    monkeypatch.setattr(
        "django_letter.notifications.checks.get_template", broken_template
    )
    errors = check_settings_template()
    assert len(errors) == 1
    assert errors[0].id == "django_letter.notifications.E002"
