from django.urls import path

from . import views

app_name = "django_letter_notifications"

urlpatterns = [
    path("settings/", views.NotificationSettingsView.as_view(), name="settings"),
    path(
        "unsubscribe/<slug:slug>/<str:token>/",
        views.NotificationUnsubscribeView.as_view(),
        name="unsubscribe",
    ),
]
