"""Shared setup for the django-letter test suite."""

# Importing the URLconf mounts the previews and imports every installed app's
# `emails` module, the same way `manage.py runserver` would.
import django_letter.urls  # noqa: F401
