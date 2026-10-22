from django.db import models
from django.db.models import CharField, F, Value
from django.db.models.functions import Concat, Lower, Trim
from django.db.models.lookups import Exact

from . import EMAIL_HASH_SALT, Notification, hash_email


class EmailLookup(Exact):
    """Compare a hashed email field with an address hash."""

    lookup_name = "email"

    def get_prep_lookup(self) -> bytes:
        return hash_email(self.rhs)

    def get_rhs_op(self, connection, rhs: str) -> str:
        return connection.operators["exact"] % rhs


class HashedEmailField(models.BinaryField):
    """Provide the `email` lookup for address hashing."""


HashedEmailField.register_lookup(EmailLookup)


class EmailHash(models.Func):
    """Return the binary hash of an email field with the package prefix."""

    output_field = models.BinaryField()

    def __init__(self, email_field: str, **extra: object) -> None:
        super().__init__(
            Concat(
                Value(EMAIL_HASH_SALT),
                Lower(Trim(F(email_field))),
                output_field=CharField(),
            ),
            **extra,
        )

    def as_sqlite(
        self, compiler, connection, **extra_context: object
    ) -> tuple[str, list[object]]:
        return super().as_sql(
            compiler,
            connection,
            template="UNHEX(SHA256(%(expressions)s))",
            **extra_context,
        )

    def as_postgresql(
        self, compiler, connection, **extra_context: object
    ) -> tuple[str, list[object]]:
        return super().as_sql(
            compiler,
            connection,
            template="DIGEST(%(expressions)s, 'sha256')",
            **extra_context,
        )

    def as_mysql(
        self, compiler, connection, **extra_context: object
    ) -> tuple[str, list[object]]:
        return super().as_sql(
            compiler,
            connection,
            template="UNHEX(SHA2(%(expressions)s, 256))",
            **extra_context,
        )

    def as_oracle(
        self, compiler, connection, **extra_context: object
    ) -> tuple[str, list[object]]:
        return super().as_sql(
            compiler,
            connection,
            template="STANDARD_HASH(%(expressions)s, 'SHA256')",
            **extra_context,
        )


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
