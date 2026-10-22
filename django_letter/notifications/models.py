from django.db import models

from django_letter.fields import HashedEmailField

from . import Notification


class NotificationPreferenceQuerySet(models.QuerySet):
    """Read and write the preferences of one address."""

    def is_enabled(self, notification: Notification, email: str) -> bool:
        """Return whether the address wants the notification."""
        try:
            return self.get(email_hash__email=email, slug=notification.slug).enabled
        except self.model.DoesNotExist:
            return notification.default

    def email_hashes(self, notification: Notification) -> models.QuerySet:
        """Return the hashes that differ from the notification's default."""
        return self.filter(
            slug=notification.slug, enabled=not notification.default
        ).values_list("email_hash", flat=True)

    def set_enabled_hash(
        self, notification: Notification, email_hash: bytes, enabled: bool
    ) -> None:
        """Turn the notification on or off for an address hash."""
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

    email_hash = HashedEmailField(max_length=32, editable=False)
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
