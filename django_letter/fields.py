import hashlib

from django.db import models
from django.db.models import CharField, F, Value
from django.db.models.functions import Concat, Lower, Trim
from django.db.models.lookups import Exact


class EmailLookup(Exact):
    """Compare a hashed email field with an address hash."""

    lookup_name = "email"

    def get_prep_lookup(self) -> bytes:
        return self.lhs.field.hash(self.rhs)

    def get_rhs_op(self, connection, rhs: str) -> str:
        return connection.operators["exact"] % rhs


class HashedEmailField(models.BinaryField):
    """Store the salted hash of an email address."""

    def __init__(
        self, *args: object, salt: str | None = None, **kwargs: object
    ) -> None:
        default = f"{type(self).__module__}.{type(self).__name__}"
        self.salt = salt if salt is not None else default
        super().__init__(*args, **kwargs)

    def deconstruct(self) -> tuple[str, str, list, dict]:
        name, path, args, kwargs = super().deconstruct()
        if self.salt != f"{type(self).__module__}.{type(self).__name__}":
            kwargs["salt"] = self.salt
        return name, path, args, kwargs

    @classmethod
    def hash_email(cls, email: str, salt: str | None = None) -> bytes:
        if salt is None:
            salt = f"{cls.__module__}.{cls.__name__}"
        return hashlib.sha256(f"{salt}:{email.strip().lower()}".encode()).digest()

    def hash(self, email: str) -> bytes:
        """Return the hash this field stores for an address."""
        return self.hash_email(email, self.salt)


HashedEmailField.register_lookup(EmailLookup)


class EmailHash(models.Func):
    """Return the binary hash of an email field with the salt prefix."""

    output_field = models.BinaryField()

    def __init__(
        self,
        email_field: str,
        *,
        salt: str | None = None,
        **extra: object,
    ) -> None:
        if salt is None:
            salt = f"{HashedEmailField.__module__}.{HashedEmailField.__name__}"
        super().__init__(
            Concat(
                Value(f"{salt}:"),
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
