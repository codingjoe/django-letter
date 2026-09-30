from __future__ import annotations

import base64
import mimetypes
from pathlib import Path

from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import translation
from django.utils.decorators import method_decorator
from django.views import generic
from django.views.decorators.clickjacking import xframe_options_exempt

from .message import TemplateEmail

MESSAGE_POLICY = "sandbox allow-same-origin; script-src 'none'"
# No origin is trusted: a picture of the app is a download like any other.
IMAGE_POLICY = "img-src data:"


def data_url(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


def preview_languages() -> dict[str, str]:
    if not settings.USE_I18N:
        return {}
    languages = {code: str(name) for code, name in settings.LANGUAGES}
    return languages if len(languages) > 1 else {}


def configured_language(language: str) -> str:
    languages = dict(settings.LANGUAGES)
    if language in languages:
        return language
    try:
        resolved = translation.get_supported_language_variant(language, strict=False)
    except LookupError:
        return language
    return resolved if resolved in languages else language


@method_decorator(xframe_options_exempt, name="dispatch")
class TemplateEmailPreviewView(generic.View):
    """
    Show one discovered subclass in desktop and mobile sized frames.

    `?plain=1` and `?raw=1` return the plain-text and bare bodies. The frames
    load the raw body, so pictures show up there as plain static URLs, never as
    `cid:` addresses. `?lang=de` switches the language and picks the entry of
    the switcher, and an unknown slug is a 404. The downloads start stopped,
    and `?load_images=1` allows them.
    """

    def get(self, request: HttpRequest, slug: str, *args, **kwargs) -> HttpResponse:
        email_class = TemplateEmail.get_email_classes().get(slug)
        if email_class is None:
            raise Http404

        language = request.GET.get("lang")
        load_images = bool(request.GET.get("load_images"))  # downloads start stopped
        if request.GET.get("plain"):
            email = email_class.render_preview(request, language=language)
            return HttpResponse(email.body, content_type="text/plain; charset=utf-8")
        if request.GET.get("raw"):
            email = email_class.render_preview(request, language=language)
            html = email.html
            # One content ID can be a prefix of another. Replace the longest first.
            for name in sorted(email.attached_static, key=len, reverse=True):
                image = email.attached_static[name]
                address = image.url if load_images else data_url(image.path)
                html = html.replace(f"cid:{name}", address)
            response = HttpResponse(html, content_type="text/html; charset=utf-8")
            policy = [MESSAGE_POLICY]
            if not load_images:
                policy.append(IMAGE_POLICY)
            response["Content-Security-Policy"] = "; ".join(policy)
            return response
        selected = configured_language(language or translation.get_language())
        languages = preview_languages()
        return render(
            request,
            "django_letter/preview.html",
            {
                "email_name": email_class.__name__,
                "list_url": reverse("django_letter:list"),
                "load_images": load_images,
                "language": selected,
                "language_name": languages.get(selected, selected),
                "languages": languages,
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
                        "module": email_class.__module__,
                        "template": email_class.template_name,
                        "url": reverse("django_letter:preview", kwargs={"slug": slug}),
                    }
                    for slug, email_class in sorted(
                        TemplateEmail.get_email_classes().items()
                    )
                ]
            },
        )
