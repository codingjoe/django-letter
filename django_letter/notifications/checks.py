from django.apps import AppConfig
from django.core.checks import CheckMessage, Error, register
from django.template import TemplateDoesNotExist
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
    except TemplateDoesNotExist:
        return [
            Error(
                "The notification settings template is missing.",
                hint=f"Add {template_name!r} to your templates.",
                id="django_letter.notifications.E002",
            )
        ]
    return []
