"""Form that reads and writes the notification preferences of one address."""

import re

from django import forms

from .api import Notification, hash_email
from .models import NotificationPreference

EMAIL_HASH_PATTERN = re.compile(r"[0-9a-f]{64}")


class NotificationFormError(ValueError):
    """Signal that the form got an unusable address or digest."""

    BOTH_GIVEN = "Pass only one of `email` or `email_hash`."
    NEITHER_GIVEN = "Pass `email` or `email_hash`."
    MALFORMED_HASH = "`email_hash` must be 64 lowercase hex characters."


class NotificationForm(forms.Form):
    """Show one checkbox for each registered kind of email."""

    def __init__(
        self,
        email: str | None = None,
        *,
        email_hash: str | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        if email:
            email = email.strip()
        if email and email_hash:
            raise NotificationFormError(NotificationFormError.BOTH_GIVEN)
        if email_hash:
            if not EMAIL_HASH_PATTERN.fullmatch(email_hash):
                raise NotificationFormError(NotificationFormError.MALFORMED_HASH)
        elif not email:
            raise NotificationFormError(NotificationFormError.NEITHER_GIVEN)
        else:
            email_hash = hash_email(email)
        self.email_hash = email_hash
        self.notifications = Notification.get_all()
        overrides = (
            {}
            if self.is_bound
            else dict(
                NotificationPreference.objects.filter(
                    email_hash=email_hash,
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
        """Store the submitted preferences for this address."""
        for notification in self.notifications:
            notification.set_enabled_hash(
                self.email_hash, self.cleaned_data[notification.slug]
            )
