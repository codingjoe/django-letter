import pytest
from django.contrib.auth.models import User
from django.db import IntegrityError

from django_letter.fields import EmailHash, HashedEmailField
from django_letter.notifications import Notification
from django_letter.notifications.models import NotificationPreference
from tests.testapp.emails import weekly_digest

pytestmark = pytest.mark.django_db

EMAIL = "ada@example.com"
PREFERENCE = {
    "slug": weekly_digest.slug,
    "email_hash": HashedEmailField.hash_email(EMAIL),
}


def test_notification_preference__str() -> None:
    preference = NotificationPreference(**PREFERENCE, enabled=False)
    assert (
        str(preference)
        == f"weekly-digest for {HashedEmailField.hash_email(EMAIL).hex()}"
    )


def test_notification_preference__is_unique_per_address_and_slug() -> None:
    NotificationPreference.objects.create(**PREFERENCE, enabled=False)
    with pytest.raises(IntegrityError):
        NotificationPreference.objects.create(**PREFERENCE, enabled=True)


def test_is_enabled__defaults_to_on() -> None:
    assert NotificationPreference.objects.is_enabled(weekly_digest, EMAIL) is True


def test_is_enabled__reads_the_override() -> None:
    NotificationPreference.objects.set_enabled_hash(
        weekly_digest, HashedEmailField.hash_email(EMAIL), False
    )
    assert NotificationPreference.objects.is_enabled(weekly_digest, EMAIL) is False


def test_is_enabled__honours_a_disabled_default() -> None:
    notification = Notification("opt-in", "Opt-in", default=False)
    assert NotificationPreference.objects.is_enabled(notification, EMAIL) is False
    NotificationPreference.objects.create(
        email_hash=HashedEmailField.hash_email(EMAIL),
        slug=notification.slug,
        enabled=True,
    )
    assert NotificationPreference.objects.is_enabled(notification, EMAIL) is True


def test_set_enabled_hash__stores_an_override_and_removes_the_default() -> None:
    digest = HashedEmailField.hash_email(EMAIL)
    NotificationPreference.objects.set_enabled_hash(weekly_digest, digest, False)
    preference = NotificationPreference.objects.get(**PREFERENCE)
    assert preference.enabled is False
    NotificationPreference.objects.set_enabled_hash(weekly_digest, digest, True)
    assert not NotificationPreference.objects.filter(**PREFERENCE).exists()


def test_email_lookup__matches_an_address() -> None:
    NotificationPreference.objects.create(**PREFERENCE, enabled=False)
    assert NotificationPreference.objects.filter(email_hash__email=EMAIL).exists()


def test_email_lookup__normalises_the_address() -> None:
    NotificationPreference.objects.create(**PREFERENCE, enabled=False)
    assert NotificationPreference.objects.filter(
        email_hash__email=" Ada@Example.COM "
    ).exists()


def test_email_lookup__misses_another_address() -> None:
    NotificationPreference.objects.create(**PREFERENCE, enabled=False)
    assert not NotificationPreference.objects.filter(
        email_hash__email="grace@example.com"
    ).exists()


def test_email_hashes__returns_disabled_overrides() -> None:
    NotificationPreference.objects.create(**PREFERENCE, enabled=False)
    assert list(NotificationPreference.objects.email_hashes(weekly_digest)) == [
        HashedEmailField.hash_email(EMAIL)
    ]


def test_email_hashes__returns_enabled_overrides() -> None:
    notification = Notification("opt-in", "Opt-in", default=False)
    NotificationPreference.objects.create(
        email_hash=HashedEmailField.hash_email(EMAIL),
        slug=notification.slug,
        enabled=True,
    )
    assert list(NotificationPreference.objects.email_hashes(notification)) == [
        HashedEmailField.hash_email(EMAIL)
    ]


def test_email_hashes__ignores_overrides_equal_to_the_default() -> None:
    NotificationPreference.objects.create(**PREFERENCE, enabled=True)
    assert not NotificationPreference.objects.email_hashes(weekly_digest).exists()


def test_email_hash__matches_hash_email() -> None:
    User.objects.create_user("ada", email=EMAIL)
    digest = (
        User.objects.annotate(hashed=EmailHash(User.get_email_field_name()))
        .values_list("hashed", flat=True)
        .get()
    )
    assert digest == HashedEmailField.hash_email(EMAIL)


def test_email_hash__normalises_the_address() -> None:
    User.objects.create_user("ada", email=" Ada@Example.COM ")
    digest = (
        User.objects.annotate(hashed=EmailHash("email"))
        .values_list("hashed", flat=True)
        .get()
    )
    assert digest == HashedEmailField.hash_email(EMAIL)


def test_email_hash__filters_opt_out_recipients() -> None:
    User.objects.create_user("ada", email=EMAIL)
    User.objects.create_user("grace", email="grace@example.com")
    NotificationPreference.objects.create(**PREFERENCE, enabled=False)
    recipients = (
        User.objects.alias(email_hash=EmailHash(User.get_email_field_name()))
        .exclude(
            email_hash__in=NotificationPreference.objects.email_hashes(weekly_digest)
        )
        .order_by("username")
    )
    assert list(recipients.values_list("username", flat=True)) == ["grace"]


def test_email_hash__filters_opt_in_recipients() -> None:
    notification = Notification("opt-in", "Opt-in", default=False)
    User.objects.create_user("ada", email=EMAIL)
    User.objects.create_user("grace", email="grace@example.com")
    NotificationPreference.objects.create(
        email_hash=HashedEmailField.hash_email("grace@example.com"),
        slug=notification.slug,
        enabled=True,
    )
    recipients = (
        User.objects.alias(email_hash=EmailHash(User.get_email_field_name()))
        .filter(
            email_hash__in=NotificationPreference.objects.email_hashes(notification)
        )
        .order_by("username")
    )
    assert list(recipients.values_list("username", flat=True)) == ["grace"]


def test_email_hash__filters_in_one_query(django_assert_num_queries) -> None:
    User.objects.create_user("ada", email=EMAIL)
    User.objects.create_user("grace", email="grace@example.com")
    NotificationPreference.objects.create(**PREFERENCE, enabled=False)
    recipients = User.objects.alias(
        email_hash=EmailHash(User.get_email_field_name())
    ).exclude(email_hash__in=NotificationPreference.objects.email_hashes(weekly_digest))
    with django_assert_num_queries(1):
        list(recipients)


@pytest.mark.parametrize(
    ("method", "sql"),
    [
        ("as_sqlite", "UNHEX(SHA256(%s))"),
        ("as_postgresql", "DIGEST(%s, 'sha256')"),
        ("as_mysql", "UNHEX(SHA2(%s, 256))"),
        ("as_oracle", "STANDARD_HASH(%s, 'SHA256')"),
    ],
)
def test_email_hash__backend_sql(method: str, sql: str) -> None:
    class Ops:
        def check_expression_support(self, expression: object) -> None:
            pass

    class Connection:
        ops = Ops()

    class Compiler:
        def compile(self, expression: object) -> tuple[str, list[object]]:
            return "%s", []

    expression = EmailHash("email")
    compiled, _ = getattr(expression, method)(Compiler(), Connection())
    assert compiled == sql
