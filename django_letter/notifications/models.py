from django.db import models


class NotificationPreference(models.Model):
    """Store one recipient's override for one notification."""

    email_hash = models.CharField(max_length=64)
    slug = models.SlugField(max_length=100)
    enabled = models.BooleanField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("email_hash", "slug"), name="unique_email_hash_slug"
            )
        ]

    def __str__(self) -> str:
        return f"{self.slug} for {self.email_hash}"
