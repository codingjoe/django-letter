"""The URLconf only mounts the preview routes in debug or test mode."""

import importlib
from typing import Any

from django.urls import clear_url_caches

import django_mail.urls


def reload_urlpatterns() -> Any:
    """Reload the URLconf so its import-time guard runs again."""
    clear_url_caches()
    return importlib.reload(django_mail.urls).urlpatterns


def test_urlpatterns_are_inert_outside_debug_and_test_env(
    settings, monkeypatch
) -> None:
    settings.DEBUG = False
    monkeypatch.setenv("DJANGO_MAIL_TEST", "false")
    assert reload_urlpatterns() == []


def test_urlpatterns_mount_in_debug(settings, monkeypatch) -> None:
    settings.DEBUG = True
    monkeypatch.setenv("DJANGO_MAIL_TEST", "false")
    assert reload_urlpatterns()


def test_urlpatterns_mount_with_test_env(settings, monkeypatch) -> None:
    settings.DEBUG = False
    monkeypatch.setenv("DJANGO_MAIL_TEST", "true")
    assert reload_urlpatterns()
