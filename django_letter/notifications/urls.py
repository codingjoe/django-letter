"""URLs for the signed notification preferences and unsubscribe links."""

from django.urls import path
from django.utils.module_loading import autodiscover_modules

from . import views

app_name = "django_letter_notifications"

# Import the `emails` module of every installed app, so production processes
# fill the registry even when the debug preview URLs are not mounted.
autodiscover_modules("emails")

urlpatterns = [
    path("<str:token>/", views.NotificationManageView.as_view(), name="manage"),
    path(
        "<str:token>/<slug:slug>/unsubscribe/",
        views.NotificationUnsubscribeView.as_view(),
        name="unsubscribe",
    ),
]
