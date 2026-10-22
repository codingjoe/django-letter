from django.db import models

from django_letter.fields import HashedEmailField


class CustomEmailHash(models.Model):
    email_hash = HashedEmailField(salt="tests.testapp", max_length=32)
