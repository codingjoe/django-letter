"""Django settings for the django-letter testapp."""

SECRET_KEY = "django-insecure-testapp-only"

DEBUG = True

ALLOWED_HOSTS = []

INSTALLED_APPS = [
    "django_letter",
    "tests.testapp",
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {},
    },
]

ROOT_URLCONF = "tests.testapp.urls"

USE_I18N = True

LANGUAGE_CODE = "en-us"

USE_TZ = True

TIME_ZONE = "UTC"
