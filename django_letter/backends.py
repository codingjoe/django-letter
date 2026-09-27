"""Email backends for the messages this package builds."""

from django.core.mail import EmailMessage
from django.core.mail.backends.console import EmailBackend as _ConsoleEmailBackend

__all__ = ["ConsoleEmailBackend"]


class ConsoleEmailBackend(_ConsoleEmailBackend):
    """Like the console email backend but only with the plain-text body."""

    def write_message(self, message: EmailMessage) -> None:
        mime_message = message.message()
        parts = mime_message.get_payload() if mime_message.is_multipart() else []
        if len(parts) < 2:
            super().write_message(message)
        else:
            # The text body is the first part, the HTML alternative and the
            # attachments follow it.
            body = parts[0]
            while body.is_multipart():
                body = body.get_payload(0)
            mime_message.set_payload(body)

            charset = mime_message.get_charset()
            msg_data = mime_message.as_bytes().decode(
                charset.get_output_charset() if charset else "utf-8"
            )
            self.stream.write(f"{msg_data}\n")
            self.stream.write("-" * 79)
            self.stream.write("\n")
            self.stream.write(f"{len(parts) - 1} more part(s) have been omitted.\n")
