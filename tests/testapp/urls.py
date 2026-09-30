"""URL configuration for the django-letter testapp."""

from django.urls import include, path
from django.views import generic

urlpatterns = [
    path("", generic.RedirectView.as_view(pattern_name="django_letter:list")),
    path("emails/", include("django_letter.urls")),
]
