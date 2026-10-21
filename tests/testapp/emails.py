"""Example emails that the preview pages list and the test suite pins."""

from collections.abc import Iterator

from django.utils.translation import gettext_lazy as _

from django_letter import TemplateEmail
from django_letter.notifications import Notification, subscribe

WEEKLY_DIGEST = Notification(
    "weekly-digest",
    _("Weekly digest"),
    _("A weekly summary of your account."),
)


class WelcomeEmail(TemplateEmail):
    """Onboard a new user with a call to action."""

    template_name = "testapp/welcome.html"
    subject = _("Welcome, %(name)s")
    preheader = _("Your account is ready, %(name)s.")

    def __init__(self, name: str = "Ada", **kwargs) -> None:
        self.name = name
        super().__init__(**kwargs)

    def get_context_data(self) -> dict[str, object]:
        return {"name": self.name}


class InvoiceEmail(TemplateEmail):
    """Deliver an invoice together with the payment terms."""

    template_name = "testapp/invoice.html"
    subject = _("Invoice %(number)s")
    preheader = _("Payment is due by %(due_date)s.")

    def __init__(
        self, number: str = "2025-001", due_date: str = "1 June", **kwargs
    ) -> None:
        self.number = number
        self.due_date = due_date
        super().__init__(**kwargs)

    def get_context_data(self) -> dict[str, object]:
        return {"number": self.number, "due_date": self.due_date}

    def gen_attachments(self) -> Iterator[tuple[str, bytes, str | None]]:
        """Attach the payment terms and the company logo."""
        yield "terms.txt", b"Payment is due within 30 days.", "text/plain"
        yield "logo.png", b"\x89PNG\r\n", None


class LogoEmail(TemplateEmail):
    """Show the new logo inside the body instead of attaching it."""

    template_name = "testapp/logo.html"
    subject = _("Say hello to our new logo")
    preheader = _("The logo sits right in the message.")


class RetinaLogoEmail(TemplateEmail):
    """Show the logo and its high-density twin inside the body."""

    template_name = "testapp/retina.html"
    subject = _("A sharper logo")
    preheader = _("Both sizes travel inside the message.")


class RemoteImagesEmail(TemplateEmail):
    """Show which pictures of a message need a download and which do not."""

    template_name = "testapp/remote.html"
    subject = _("News from the workshop")
    preheader = _("Our logo needs no download.")


@subscribe(WEEKLY_DIGEST)
class WeeklyDigestEmail(TemplateEmail):
    """Deliver a summary of account activity with a link to stop the updates."""

    template_name = "testapp/digest.html"
    subject = _("Your weekly digest")
    preheader = _("A summary of your account this week.")

    def __init__(self, to: str | list[str] = "ada@example.com", **kwargs) -> None:
        super().__init__(to=[to] if isinstance(to, str) else to, **kwargs)
