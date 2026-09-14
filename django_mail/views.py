from __future__ import annotations

from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import generic
from django.views.decorators.clickjacking import xframe_options_exempt

from .message import TemplateEmail


@method_decorator(xframe_options_exempt, name="dispatch")
class TemplateEmailPreviewView(generic.View):
    """
    Show one discovered subclass in desktop and mobile sized frames.

    `?plain=1` and `?raw=1` return the plain-text and bare HTML bodies, `?lang=de`
    switches the language, and an unknown slug is a 404.
    """

    def get(self, request: HttpRequest, slug: str, *args, **kwargs) -> HttpResponse:
        email_class = TemplateEmail.get_email_classes().get(slug)
        if email_class is None:
            raise Http404

        language = request.GET.get("lang")
        if request.GET.get("plain"):
            email = email_class.render_preview(request, language=language)
            return HttpResponse(email.body, content_type="text/plain; charset=utf-8")
        if request.GET.get("raw"):
            email = email_class.render_preview(request, language=language)
            return HttpResponse(email.html, content_type="text/html; charset=utf-8")
        return render(
            request,
            "django_mail/preview.html",
            {
                "email_name": email_class.__name__,
                "list_url": reverse("django_mail:list"),
            },
        )


class TemplateEmailListView(generic.View):
    def get(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        return render(
            request,
            "django_mail/list.html",
            {
                "emails": [
                    {
                        "name": email_class.__name__,
                        "url": reverse("django_mail:preview", kwargs={"slug": slug}),
                    }
                    for slug, email_class in sorted(
                        TemplateEmail.get_email_classes().items()
                    )
                ]
            },
        )
