"""URL configuration for the django-letter testapp."""

from django.urls import include, path

urlpatterns = [
    path("emails/", include("django_letter.urls")),
]
