from django.apps import AppConfig
from django.core.checks import CheckMessage, Error, register
from django.template import TemplateDoesNotExist, TemplateSyntaxError
from django.template.loader import get_template
from django.urls import NoReverseMatch, reverse

from .views import NotificationSettingsView


@register()
def check_unsubscribe_url(
    app_configs: list[AppConfig] | None = None, **kwargs: object
) -> list[CheckMessage]:
    try:
        reverse(
            "django_letter_notifications:unsubscribe",
            kwargs={"slug": "example", "token": "example"},
        )
    except NoReverseMatch:
        return [
            Error(
                "The notification URLs are not mounted.",
                hint="Include 'django_letter.notifications.urls' in your URLconf.",
                id="django_letter.notifications.E001",
            )
        ]
    return []


@register()
def check_settings_template(
    app_configs: list[AppConfig] | None = None, **kwargs: object
) -> list[CheckMessage]:
    template_name = NotificationSettingsView.template_name
    try:
        get_template(template_name)
    except TemplateDoesNotExist, TemplateSyntaxError:
        return [
            Error(
                "The notification settings template cannot be loaded.",
                hint=f"Add or correct {template_name!r}.",
                id="django_letter.notifications.E002",
            )
        ]
    return []
