import logging
import mimetypes
import typing
from collections.abc import Iterable, Iterator
from email import encoders
from email.message import Message, MIMEPart
from email.mime.base import MIMEBase
from email.utils import formataddr, getaddresses
from pathlib import Path

import django
from django.conf import settings
from django.contrib.staticfiles import finders
from django.core.mail import EmailMultiAlternatives
from django.http import HttpRequest
from django.template import loader
from django.templatetags.static import static
from django.urls import NoReverseMatch
from django.utils import translation
from django.utils.text import slugify
from premailer import premailer

from .exceptions import (
    EmailImproperlyConfigured,
    InactiveUserError,
    MissingEmailError,
)
from .notifications.api import Notification, hash_email
from .parser import html_to_text

if typing.TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser

__all__ = ["TemplateEmail"]

EMAIL_CONTEXT_KEY = "_django_letter_email"


class StaticImage(typing.NamedTuple):
    """Pair the file of a picture with the address a browser loads it from."""

    path: Path
    url: str


class NotificationLinks(typing.NamedTuple):
    """Pair the opt-out link with the preferences link."""

    unsubscribe: str
    manage: str


def _attached_static_part(path: Path, content_id: str) -> Message:
    maintype, _, subtype = (
        mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    ).partition("/")
    content = path.read_bytes()
    # attach() takes MIMEPart from Django 6.0 on and MIMEBase below it.
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


def _recipient_list(recipients: str | Iterable[str]) -> list[str]:
    """Return one field as a list of entries."""
    return [recipients] if isinstance(recipients, str) else list(recipients)


def _addresses(*recipient_fields: str | Iterable[str]) -> list[str]:
    """Collect the lower-case mailbox part of every entry in the given fields."""
    return [
        address.lower()
        for field in recipient_fields
        for _, address in getaddresses(_recipient_list(field))
        if address
    ]


class TemplateEmail(EmailMultiAlternatives):
    """
    Render the HTML body and its plain-text alternative.

    The markup comes from `template_name`.
    """

    template_name: str = ""
    subject: str = ""
    preheader: str = ""
    base_url: str | None = None
    html: str | None = None
    attached_static: dict[str, StaticImage]
    notification: Notification | None = None

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
        self._notification_links: tuple[str, NotificationLinks] | None = None
        super().__init__(**{"subject": self.subject} | kwargs)

    @classmethod
    def to_user(cls, user: AbstractUser, **kwargs) -> TemplateEmail:
        """
        Return an email addressed to the given recipient.

        The full name becomes the display name, and the user joins the template
        context. Pass the values of the subclass and `language` as keyword
        arguments. The `to=` and `extra_context` values are set here.

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
        if (links := self.get_notification_urls()) and "list-unsubscribe" not in {
            header.lower() for header in self.extra_headers
        }:
            self.extra_headers["List-Unsubscribe"] = f"<{links.unsubscribe}>"
            self.extra_headers["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
        return super().message(**kwargs)

    def send(self, fail_silently: bool = False, **kwargs) -> int:
        """
        Deliver to a recipient who still wants this notification.

        A decorated message may name zero or one distinct recipient across
        `to`, `cc`, and `bcc`. With zero, nothing is delivered and the call
        returns `0`. With more than one, it raises `EmailImproperlyConfigured`
        before any mail leaves, because the links sign one address. When the
        recipient's preference is off, nothing is delivered either.
        """
        if not (notification := self.notification):
            return super().send(fail_silently, **kwargs)
        if not (address := self._notification_address()):
            return 0
        if not notification.is_enabled(address):
            return 0
        return super().send(fail_silently, **kwargs)

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

    def _notification_address(self) -> str | None:
        """
        Return the one mailbox across `to`, `cc`, and `bcc` that a link can sign.

        Addresses compare case-insensitively. Return `None` when the message
        names none. Raise `EmailImproperlyConfigured` when it names more than
        one.
        """
        addresses = set(_addresses(self.to, self.cc, self.bcc))
        if len(addresses) > 1:
            raise EmailImproperlyConfigured(
                type(self), "cannot sign a link for multiple recipients"
            )
        return next(iter(addresses), None)

    def get_notification_urls(self) -> NotificationLinks | None:
        """
        Return the opt-out and preferences links, when they apply.

        A decorated class with one distinct mailbox across `to`, `cc`, and
        `bcc` gets links. A message that names none renders without them.
        Raise `EmailImproperlyConfigured` when the message names more than one,
        when the subapp routes are not mounted, or when a rendered message is
        reused for another recipient. The links are signed once and cached with
        the address they belong to.
        """
        if not (notification := self.notification):
            return None
        if not (address := self._notification_address()):
            return None
        if self._notification_links:
            signed_for, links = self._notification_links
            if signed_for == address:
                return links
            if self.html is not None:
                raise EmailImproperlyConfigured(
                    type(self),
                    "cannot reuse a rendered message for another recipient",
                )
        email_hash = hash_email(address)
        base_url = self.get_base_url()
        try:
            links = NotificationLinks(
                notification.unsubscribe_url(base_url, email_hash),
                notification.manage_url(base_url, email_hash),
            )
        except NoReverseMatch:
            raise EmailImproperlyConfigured(
                type(self),
                "cannot build notification links."
                " Mount 'django_letter.notifications.urls'",
            ) from None
        self._notification_links = address, links
        return links

    def render_html(self, **context) -> str:
        """
        Return the body markup with the stylesheet applied.

        `subject` and `preheader` join the context, and everything uses the
        language of the message. A decorated message also adds `notification`.
        With one distinct mailbox across `to`, `cc`, and `bcc` it adds
        `unsubscribe_url` and `manage_notifications_url`. With none it adds
        neither, and with more than one it raises `EmailImproperlyConfigured`.
        The first link opens a confirmation page, and only its POST disables
        the notification. Pictures that the template asks for with
        `{% attached_static %}` register on this message.
        """
        with translation.override(self.language):
            self.subject = str(self.get_subject(**context))
            context["subject"] = self.subject
            context["preheader"] = str(self.get_preheader(**context))
            template = loader.get_template(self.get_template())
            context[EMAIL_CONTEXT_KEY] = self
            if notification := self.notification:
                context["notification"] = notification
            if links := self.get_notification_urls():
                context["unsubscribe_url"] = links.unsubscribe
                context["manage_notifications_url"] = links.manage
            return premailer.transform(
                html=template.render(context),
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

    def attach_static(self, name: str) -> str:
        """
        Register the file that the finders resolve for `name` on this message.

        The content ID is the base name of the path, so the body gets
        `cid:<base name>`. The file and its URL go into `attached_static`, and
        asking again for the same file returns the same address.

        Raises:
            EmailImproperlyConfigured: If the file is nowhere to be found, or
                two different files share a base name.
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
            base_url=request.build_absolute_uri("/") if request else None,
            **kwargs,
        )
        email.render(**(context or {}))
        return email
