import os

from django.conf import settings
from django.urls import path
from django.utils.module_loading import autodiscover_modules

from . import views

app_name = "django_letter"

if settings.DEBUG or os.environ.get("DJANGO_LETTER_TEST") == "true":
    # Import the `emails` module of every installed app, the same way Django
    # imports `admin.py`, so the previews have something to list.
    autodiscover_modules("emails")
    urlpatterns = [
        path("", views.TemplateEmailListView.as_view(), name="list"),
        path(
            "messages/<slug:slug>/",
            views.TemplateEmailPreviewView.as_view(),
            name="preview",
        ),
    ]
else:
    urlpatterns = []
