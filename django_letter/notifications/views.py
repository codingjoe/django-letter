import typing

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import PermissionDenied, SuspiciousOperation
from django.core.signing import BadSignature, b64_decode
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, resolve_url
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import generic
from django.views.decorators.csrf import csrf_exempt

from . import registry, signer
from .forms import NotificationForm
from .models import NotificationPreference


class NotificationSettingsView(LoginRequiredMixin, generic.FormView):
    """Show and save the notification preferences of the signed-in user."""

    form_class = NotificationForm
    template_name = "django_letter/notification_form.html"

    def get_form_kwargs(self) -> dict[str, typing.Any]:
        kwargs = super().get_form_kwargs()
        email_field = getattr(
            self.request.user, "EMAIL_FIELD", AbstractUser.EMAIL_FIELD
        )
        kwargs["email"] = getattr(self.request.user, email_field, "")
        return kwargs

    def form_valid(self, form: NotificationForm) -> HttpResponse:
        form.save()
        return super().form_valid(form)

    def get_success_url(self) -> str:
        return reverse("django_letter_notifications:settings")


@method_decorator(csrf_exempt, name="dispatch")
class NotificationUnsubscribeView(generic.View):
    """Disable one notification and redirect to the settings page."""

    def get(self, request: HttpRequest, token: str, slug: str) -> HttpResponse:
        email_hash = self.decode_token(token)
        if notification := registry.get(slug):
            NotificationPreference.objects.set_enabled_hash(
                notification, email_hash, False
            )
        return redirect(self.get_redirect_url())

    post = get

    @staticmethod
    def decode_token(token: str) -> bytes:
        try:
            payload = signer.unsign(token)
        except BadSignature as error:
            raise PermissionDenied from error
        try:
            email_hash = b64_decode(payload.encode())
        except ValueError as error:
            raise SuspiciousOperation from error
        if len(email_hash) != 32:
            raise SuspiciousOperation
        return email_hash

    @staticmethod
    def get_redirect_url() -> str:
        return resolve_url(
            getattr(
                settings,
                "UNSUBSCRIBE_REDIRECT_URL",
                "django_letter_notifications:settings",
            )
        )
