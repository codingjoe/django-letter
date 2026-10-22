from django.db import migrations, models

import django_letter.notifications.models


def create_pgcrypto(apps, schema_editor) -> None:
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.RunPython(create_pgcrypto, migrations.RunPython.noop),
        migrations.CreateModel(
            name="NotificationPreference",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "email_hash",
                    django_letter.notifications.models.HashedEmailField(
                        editable=False, max_length=32
                    ),
                ),
                ("slug", models.SlugField(max_length=100)),
                ("enabled", models.BooleanField()),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.AddConstraint(
            model_name="notificationpreference",
            constraint=models.UniqueConstraint(
                fields=("email_hash", "slug"), name="unique_email_hash_slug"
            ),
        ),
    ]
