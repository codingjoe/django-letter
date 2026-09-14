"""Example emails that the preview pages list and the test suite pins."""

from __future__ import annotations

from collections.abc import Iterator

from django.utils.translation import gettext_lazy as _

from django_mail import TemplateEmail


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
