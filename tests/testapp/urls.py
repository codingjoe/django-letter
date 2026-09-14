"""URL configuration for the django-mail testapp."""

from django.urls import include, path

urlpatterns = [
    path("emails/", include("django_mail.urls")),
]
