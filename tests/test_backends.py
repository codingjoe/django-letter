"""Behaviour of the console email backend."""

import io

from django.core.mail import EmailMessage

from django_letter.backends import ConsoleEmailBackend
from tests.testapp.emails import InvoiceEmail, WelcomeEmail


def console_output(email: EmailMessage) -> str:
    """Send `email` and return everything the backend prints."""
    stream = io.StringIO()
    with ConsoleEmailBackend(stream=stream) as connection:
        connection.send_messages([email])
    return stream.getvalue()


def test_prints_the_text_body() -> None:
    output = console_output(WelcomeEmail(language="en", to=["ada@example.com"]))
    assert "Subject: Welcome, Ada" in output
    assert "Your account is ready, Ada. Welcome, Ada" in output
    assert "Confirm address <http://testserver/welcome/confirm>" in output


def test_leaves_out_the_html_alternative() -> None:
    output = console_output(WelcomeEmail(language="en", to=["ada@example.com"]))
    assert "<html" not in output
    assert "background-color" not in output  # the inlined stylesheet
    assert "1 more part(s) have been omitted." in output


def test_leaves_out_the_attachments() -> None:
    output = console_output(InvoiceEmail(language="en", to=["ada@example.com"]))
    assert "Payment is due by 1 June. The payment terms are attached." in output
    assert "Payment is due within 30 days." not in output  # the terms attachment
    assert "2 more part(s) have been omitted." in output


def test_prints_messages_without_alternative_parts_unchanged() -> None:
    email = EmailMessage(
        subject="Plain",
        body="Just text.",
        from_email="billing@example.com",
        to=["ada@example.com"],
    )
    output = console_output(email)
    assert "Just text." in output
    assert "omitted" not in output
