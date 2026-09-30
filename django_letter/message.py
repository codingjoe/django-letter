from __future__ import annotations

import contextvars
import logging
import mimetypes
import typing
from collections.abc import Iterator
from email import encoders
from email.message import Message, MIMEPart
from email.mime.base import MIMEBase
from email.utils import formataddr
from pathlib import Path

import django
from django.conf import settings
from django.contrib.staticfiles import finders
from django.core.mail import EmailMultiAlternatives
from django.http import HttpRequest
from django.template import loader
from django.templatetags.static import static
from django.utils import translation
from django.utils.text import slugify
from premailer import premailer

from .exceptions import (
    EmailImproperlyConfigured,
    InactiveUserError,
    MissingEmailError,
)
from .parser import html_to_text

if typing.TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser

__all__ = ["TemplateEmail"]

_CURRENT_EMAIL: contextvars.ContextVar[TemplateEmail | None] = contextvars.ContextVar(
    "django_letter_current_email"
)


class StaticImage(typing.NamedTuple):
    """
    Pair the file of a picture with the address a browser loads it from.

    `attached_static` maps each content ID to one of these: `path` points at the
    file on disk and `url` at the address the debug pages and web views use.
    """

    path: Path
    url: str


def _attached_static_part(path: Path, content_id: str) -> Message:
    """
    Return the inline part that carries the picture stored at `path`.

    Django 6.0 hands `MIMEPart` objects to `attach()`, earlier versions know
    `MIMEBase` only. Both shapes carry the content type that `mimetypes` guesses
    from the file name, base64 encoding, an inline disposition and
    `Content-ID: <content_id>`; `MIMEBase` adds `MIME-Version: 1.0`, like the
    attachments Django builds on that version itself.
    """
    maintype, _, subtype = (
        mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    ).partition("/")
    content = path.read_bytes()
    if django.VERSION >= (6, 0):
        part = MIMEPart()
        part.set_content(
            content,
            maintype=maintype,
            subtype=subtype,
            disposition="inline",
            cid=f"<{content_id}>",
        )
        return part
    part = MIMEBase(maintype, subtype)
    part.set_payload(content)
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", "inline")
    part.add_header("Content-ID", f"<{content_id}>")
    return part


class TemplateEmail(EmailMultiAlternatives):
    """Render the HTML and plain-text bodies of one Django template."""

    template_name: str = ""
    subject: str = ""
    preheader: str = ""
    base_url: str | None = None
    html: str | None = None
    attached_static: dict[str, StaticImage]

    @classmethod
    def slug(cls) -> str:
        return slugify(cls.__name__)

    @classmethod
    def get_email_classes(cls) -> dict[str, type[TemplateEmail]]:
        """
        Collect every renderable subclass, keyed by preview URL.

        A subclass counts once it defines both `template_name` and `subject`.
        """
        classes: dict[str, type[TemplateEmail]] = {}
        for subclass in cls.__subclasses__():
            if subclass.template_name and subclass.subject:
                classes[subclass.slug()] = subclass
            classes |= subclass.get_email_classes()
        return classes

    def __init__(
        self,
        language: str | None = None,
        base_url: str | None = None,
        extra_context: dict[str, typing.Any] | None = None,
        **kwargs,
    ) -> None:
        """Set the language of this message and fill the class defaults."""
        if settings.USE_I18N and not language:
            raise EmailImproperlyConfigured(type(self), "is missing a language")
        self.language = language or translation.get_language()
        self.base_url = base_url or type(self).base_url
        self.extra_context = extra_context or {}
        self.attached_static = {}
        super().__init__(**{"subject": self.subject} | kwargs)

    @classmethod
    def to_user(cls, user: AbstractUser, **kwargs) -> TemplateEmail:
        """
        Return an email addressed to the given recipient.

        The full name becomes the display name, and the user joins the template
        context. Pass the values of the subclass and `language` as keyword
        arguments; `to=` and `extra_context` are set here.

        Raises:
            InactiveUserError: If the recipient is deactivated.
            MissingEmailError: If the recipient has no email address.
        """
        if email := getattr(user, user.EMAIL_FIELD):
            if user.is_active:
                return cls(
                    to=[formataddr((user.get_full_name(), email))],
                    extra_context={"user": user},
                    **kwargs,
                )
            raise InactiveUserError(user)
        raise MissingEmailError(user)

    def message(self, **kwargs) -> Message:
        self.render()
        return super().message(**kwargs)

    def get_template(self) -> str:
        """Return the configured markup, raising `ImproperlyConfigured` when unset."""
        if not self.template_name:
            raise EmailImproperlyConfigured(type(self), "is missing a template")
        return self.template_name

    def get_context_data(self) -> dict[str, typing.Any]:
        """
        Return the values the template needs.

        An override calls `super().get_context_data()` to keep `extra_context`.
        """
        return {**self.extra_context}

    def get_subject(self, **context) -> str:
        """
        Interpolate the `%(name)s` placeholders of the configured line.

        Raise `ImproperlyConfigured` when a subclass leaves that line empty.
        """
        if not self.subject:
            raise EmailImproperlyConfigured(type(self), "is missing a subject")
        return self.subject % context

    def get_preheader(self, **context) -> str:
        """
        Return the hidden line that inboxes show next to the subject.

        It fills its `%(name)s` placeholders from the context of the template.
        """
        return self.preheader % context

    def get_base_url(self) -> str:
        """
        Return the prefix that resolves relative links and image sources.

        The `base_url` attribute wins. Without it, the address comes from the
        first usable `ALLOWED_HOSTS` entry, with `https` when the project sits
        behind a TLS-terminating proxy or sends HSTS headers.
        """
        if self.base_url:
            return self.base_url
        if (
            host := next(
                (host for host in settings.ALLOWED_HOSTS if host and host != "*"), None
            )
        ) is None:
            raise EmailImproperlyConfigured(
                type(self),
                "cannot build a base URL."
                " Set `base_url` or add a host to ALLOWED_HOSTS",
            )
        secure = settings.SECURE_PROXY_SSL_HEADER or settings.SECURE_HSTS_SECONDS
        return f"{'https' if secure else 'http'}://{host.removeprefix('.')}"

    def render_html(self, **context) -> str:
        """
        Return the body markup with the stylesheet applied.

        `subject` and `preheader` join the context, and everything renders in the
        language of the message. While the template renders, every
        `{% attached_static %}` call registers its picture on this message.
        """
        with translation.override(self.language):
            self.subject = str(self.get_subject(**context))
            context["subject"] = self.subject
            context["preheader"] = str(self.get_preheader(**context))
            template = loader.get_template(self.get_template())
            token = _CURRENT_EMAIL.set(self)
            try:
                html = template.render(context)
            finally:
                _CURRENT_EMAIL.reset(token)
            return premailer.transform(
                html=html,
                base_url=self.get_base_url(),
                strip_important=False,
                cssutils_logging_level=logging.ERROR,
            )

    def render_body(self, html: str) -> str:
        return html_to_text(html)

    def gen_attachments(self) -> Iterator[tuple[str, bytes, str | None]]:
        """
        Yield the files the message carries.

        A `None` MIME type lets Python guess from the file name.
        """
        yield from ()

    @classmethod
    def current(cls) -> TemplateEmail | None:
        """
        Return the message that renders right now, if any.

        Everywhere else it is `None`, so `{% attached_static %}` falls back to
        the plain static URL.
        """
        return _CURRENT_EMAIL.get(None)

    def attach_static(self, name: str) -> str:
        """
        Register the static file `name` as a picture of this message.

        The file resolves through the static file finders, and its base name
        becomes the content ID, so `images/logo.png` returns `cid:logo.png`.
        Repeating the call returns the same address, and `attached_static` pairs
        the content ID with the file and the URL that the debug pages show.

        Raises:
            EmailImproperlyConfigured: If no finder resolves the file, or two
                different files share a base name.
        """
        if not (found := finders.find(name)) or not Path(found).is_file():
            raise EmailImproperlyConfigured(
                type(self), f"cannot find the static file {name}"
            )
        content_id = Path(name).name
        path = Path(found)
        if (image := self.attached_static.get(content_id)) and image.path != path:
            raise EmailImproperlyConfigured(
                type(self), f"cannot attach two static files named {content_id}"
            )
        self.attached_static[content_id] = StaticImage(path, static(name))
        return f"cid:{content_id}"

    def render(self, **context: typing.Any) -> None:
        if self.html is None:
            self.html = self.render_html(**(self.get_context_data() | context))
            self.body = self.render_body(self.html)
            self.attach_alternative(self.html, "text/html")
            for filename, content, mime_type in self.gen_attachments():
                self.attach(filename, content, mime_type)
            for content_id, image in self.attached_static.items():
                self.attach(_attached_static_part(image.path, content_id))

    @classmethod
    def render_preview(
        cls,
        request: HttpRequest | None = None,
        *,
        context: dict[str, typing.Any] | None = None,
        language: str | None = None,
        **kwargs,
    ) -> TemplateEmail:
        """
        Return the rendered email shown by the debug pages.

        `context` merges over `get_context_data()`, and the other keyword
        arguments reach the constructor as a sender would pass them.
        """
        email = cls(
            language=language or translation.get_language(),
            base_url=request.build_absolute_uri() if request else None,
            **kwargs,
        )
        email.render(**(context or {}))
        return email
