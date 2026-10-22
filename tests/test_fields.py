import hashlib

import pytest
from django.contrib.auth.models import User

from django_letter.fields import EmailHash, HashedEmailField
from django_letter.notifications.models import NotificationPreference
from tests.testapp.models import CustomEmailHash

pytestmark = pytest.mark.django_db

EMAIL = "ada@example.com"
SALT = "tests.testapp"


def test_hash_email__normalises_the_address() -> None:
    field = HashedEmailField()
    assert field.hash_email(" Ada@Example.COM ") == field.hash_email(EMAIL)


def test_hash_email__is_salted() -> None:
    assert (
        HashedEmailField().hash_email(EMAIL) != hashlib.sha256(EMAIL.encode()).digest()
    )


def test_hash_email__returns_a_32_byte_digest() -> None:
    assert len(HashedEmailField().hash_email(EMAIL)) == 32


def test_hash_email__uses_the_given_salt() -> None:
    assert HashedEmailField().hash_email(EMAIL) != HashedEmailField(
        salt=SALT
    ).hash_email(EMAIL)


def test_hashed_email_field__hashes_with_its_own_salt() -> None:
    field = CustomEmailHash._meta.get_field("email_hash")
    CustomEmailHash.objects.create(email_hash=field.hash_email(EMAIL))
    assert CustomEmailHash.objects.filter(email_hash__email=EMAIL).exists()


def test_hashed_email_field__misses_a_hash_with_the_default_salt() -> None:
    CustomEmailHash.objects.create(email_hash=HashedEmailField().hash_email(EMAIL))
    assert not CustomEmailHash.objects.filter(email_hash__email=EMAIL).exists()


def test_hashed_email_field__deconstructs_a_custom_salt() -> None:
    _, _, _, kwargs = CustomEmailHash._meta.get_field("email_hash").deconstruct()
    assert kwargs["salt"] == SALT


def test_hashed_email_field__hashes_an_address() -> None:
    field = CustomEmailHash._meta.get_field("email_hash")
    assert field.hash_email(EMAIL) == HashedEmailField(salt=SALT).hash_email(EMAIL)


def test_hashed_email_field__omits_the_default_salt() -> None:
    _, _, _, kwargs = NotificationPreference._meta.get_field("email_hash").deconstruct()
    assert "salt" not in kwargs


def test_hashed_email_field__derives_the_default_salt_from_the_class() -> None:
    field = NotificationPreference._meta.get_field("email_hash")
    assert field.salt == "django_letter.fields.HashedEmailField"


def test_email_hash__uses_the_given_salt() -> None:
    User.objects.create_user("ada", email=EMAIL)
    digest = (
        User.objects.annotate(hashed=EmailHash(User.get_email_field_name(), salt=SALT))
        .values_list("hashed", flat=True)
        .get()
    )
    assert digest == HashedEmailField(salt=SALT).hash_email(EMAIL)
