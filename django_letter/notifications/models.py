from django.db import models

from . import Notification, hash_email


class NotificationPreferenceQuerySet(models.QuerySet):
    """Read and write the preferences of one address."""

    def is_enabled(self, notification: Notification, email: str) -> bool:
        """Return whether the address wants the notification."""
        try:
            return self.get(
                email_hash=hash_email(email), slug=notification.slug
            ).enabled
        except self.model.DoesNotExist:
            return notification.default

    def set_enabled_hash(
        self, notification: Notification, email_hash: bytes, enabled: bool
    ) -> None:
        """Turn the notification on or off for an address digest."""
        if enabled == notification.default:
            self.filter(email_hash=email_hash, slug=notification.slug).delete()
            return
        self.update_or_create(
            email_hash=email_hash,
            slug=notification.slug,
            defaults={"enabled": enabled},
        )


class NotificationPreference(models.Model):
    """Store one recipient's override for one notification."""

    email_hash = models.BinaryField(max_length=32, editable=False)
    slug = models.SlugField(max_length=100)
    enabled = models.BooleanField()
    updated_at = models.DateTimeField(auto_now=True)

    objects = NotificationPreferenceQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("email_hash", "slug"), name="unique_email_hash_slug"
            )
        ]

    def __str__(self) -> str:
        return f"{self.slug} for {self.email_hash.hex()}"
