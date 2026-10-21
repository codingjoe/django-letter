from django.apps import AppConfig
from django.utils.module_loading import autodiscover_modules


class NotificationConfig(AppConfig):
    """Configure the optional notification preference app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "django_letter.notifications"
    label = "django_letter_notifications"

    def ready(self) -> None:
        autodiscover_modules("emails")
        from . import checks  # noqa: F401
