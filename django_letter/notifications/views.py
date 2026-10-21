"""Views behind the signed notification links."""

from django.core.signing import BadSignature
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import generic
from django.views.decorators.csrf import csrf_exempt

from .api import Notification, unsign_email_hash
from .forms import EMAIL_HASH_PATTERN, NotificationForm

TEMPLATE_FORM = "django_letter_notifications/notification_form.html"
TEMPLATE_UNSUBSCRIBE = "django_letter_notifications/notification_unsubscribe.html"
TEMPLATE_UNSUBSCRIBED = "django_letter_notifications/notification_unsubscribed.html"


def decode_token(token: str) -> str:
    """Return the digest behind a signed link, or raise `Http404` when invalid."""
    try:
        email_hash = unsign_email_hash(token)
    except BadSignature as error:
        raise Http404 from error
    if not EMAIL_HASH_PATTERN.fullmatch(email_hash):
        raise Http404
    return email_hash


class NotificationManageView(generic.View):
    """Show the preferences form and store the submitted choices for one address."""

    def get(self, request: HttpRequest, token: str) -> HttpResponse:
        form = NotificationForm(email_hash=decode_token(token))
        return render(
            request,
            TEMPLATE_FORM,
            {"form": form, "saved": "saved" in request.GET},
        )

    def post(self, request: HttpRequest, token: str) -> HttpResponse:
        form = NotificationForm(email_hash=decode_token(token), data=request.POST)
        form.full_clean()
        form.save()
        return redirect(f"{request.path}?saved=1")


@method_decorator(csrf_exempt, name="dispatch")
class NotificationUnsubscribeView(generic.View):
    """Ask for confirmation, then disable the kind only on POST."""

    def get(self, request: HttpRequest, token: str, slug: str) -> HttpResponse:
        decode_token(token)
        notification = Notification.find(slug)
        return render(
            request,
            TEMPLATE_UNSUBSCRIBE,
            self.get_context(token, notification.name if notification else slug),
        )

    def post(self, request: HttpRequest, token: str, slug: str) -> HttpResponse:
        email_hash = decode_token(token)
        notification = Notification.find(slug)
        if notification:
            notification.set_enabled_hash(email_hash, False)
        return render(
            request,
            TEMPLATE_UNSUBSCRIBED,
            self.get_context(token, notification.name if notification else slug),
        )

    @staticmethod
    def get_context(token: str, name: str) -> dict[str, str]:
        return {
            "name": name,
            "manage_url": reverse(
                "django_letter_notifications:manage", kwargs={"token": token}
            ),
        }
