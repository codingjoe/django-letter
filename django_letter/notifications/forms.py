from django import forms

from . import hash_email, registry
from .models import NotificationPreference


class NotificationForm(forms.Form):
    """Show one checkbox for each registered kind of email."""

    def __init__(self, email: str, **kwargs) -> None:
        super().__init__(**kwargs)
        email = email.strip()
        if not email:
            raise ValueError("Pass a non-empty `email`.")  # noqa: TRY003
        self.email_hash = hash_email(email)
        self.notifications = tuple(registry.values())
        overrides = (
            {}
            if self.is_bound
            else dict(
                NotificationPreference.objects.filter(
                    email_hash=self.email_hash,
                    slug__in=[notification.slug for notification in self.notifications],
                ).values_list("slug", "enabled")
            )
        )
        for notification in self.notifications:
            self.fields[notification.slug] = forms.BooleanField(
                label=notification.name,
                help_text=notification.help_text,
                initial=overrides.get(notification.slug, notification.default),
                required=False,
            )

    def save(self) -> None:
        for notification in self.notifications:
            NotificationPreference.objects.set_enabled_hash(
                notification,
                self.email_hash,
                self.cleaned_data[notification.slug],
            )
