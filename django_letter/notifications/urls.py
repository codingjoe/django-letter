from django.urls import path
from django.utils.module_loading import autodiscover_modules

from . import views

app_name = "django_letter_notifications"

autodiscover_modules("emails")

urlpatterns = [
    path("settings/", views.NotificationSettingsView.as_view(), name="settings"),
    path(
        "unsubscribe/<slug:slug>/<str:token>/",
        views.NotificationUnsubscribeView.as_view(),
        name="unsubscribe",
    ),
]
