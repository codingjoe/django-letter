from __future__ import annotations

from urllib.parse import urlsplit

from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import generic
from django.views.decorators.clickjacking import xframe_options_exempt

from .message import TemplateEmail


def image_policy() -> str:
    """
    Return the policy that keeps pictures of other hosts out of the preview.

    The pictures the app serves itself stay visible: same-origin URLs, `data:`
    addresses, and the host of an absolute `STATIC_URL`.
    """
    sources = ["'self'", "data:"]
    if (static := urlsplit(str(settings.STATIC_URL))).netloc:
        sources.append(f"{static.scheme}://{static.netloc}")
    return "img-src " + " ".join(sources)


@method_decorator(xframe_options_exempt, name="dispatch")
class TemplateEmailPreviewView(generic.View):
    """
    Show one discovered subclass in desktop and mobile sized frames.

    `?plain=1` and `?raw=1` return the plain-text and bare bodies. The frames
    load the raw body, so pictures show up there as plain static URLs, never as
    `cid:` addresses. `?lang=de` switches the language, and an unknown slug is a
    404. `?block_images=1` sends the raw body with an `img-src` policy, so the
    browser loads the pictures of the app and skips the ones other hosts serve,
    the way clients stop tracking pixels.
    """

    def get(self, request: HttpRequest, slug: str, *args, **kwargs) -> HttpResponse:
        email_class = TemplateEmail.get_email_classes().get(slug)
        if email_class is None:
            raise Http404

        language = request.GET.get("lang")
        block_images = bool(request.GET.get("block_images"))
        if request.GET.get("plain"):
            email = email_class.render_preview(request, language=language)
            return HttpResponse(email.body, content_type="text/plain; charset=utf-8")
        if request.GET.get("raw"):
            email = email_class.render_preview(request, language=language)
            html = email.html
            # One content ID can be a prefix of another. Replace the longest first.
            for name in sorted(email.attached_static, key=len, reverse=True):
                html = html.replace(f"cid:{name}", email.attached_static[name].url)
            response = HttpResponse(html, content_type="text/html; charset=utf-8")
            if block_images:
                response["Content-Security-Policy"] = image_policy()
            return response
        return render(
            request,
            "django_letter/preview.html",
            {
                "email_name": email_class.__name__,
                "list_url": reverse("django_letter:list"),
                "block_images": block_images,
            },
        )


class TemplateEmailListView(generic.View):
    def get(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        return render(
            request,
            "django_letter/list.html",
            {
                "emails": [
                    {
                        "name": email_class.__name__,
                        "url": reverse("django_letter:preview", kwargs={"slug": slug}),
                    }
                    for slug, email_class in sorted(
                        TemplateEmail.get_email_classes().items()
                    )
                ]
            },
        )
