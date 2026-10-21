from django.apps import AppConfig


class NotificationConfig(AppConfig):
    """Configure the optional notification preference app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "django_letter.notifications"
    label = "django_letter_notifications"
