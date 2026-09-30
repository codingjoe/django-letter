from django import template
from django.templatetags.static import static
from django.utils.html import format_html, format_html_join

from ..message import EMAIL_CONTEXT_KEY

register = template.Library()


@register.simple_tag(takes_context=True)
def attached_static(context: template.Context, name: str) -> str:
    """
    Return the address of a picture that travels inside the message.

    Takes the path `{% static %}` takes. A picture asked for while a message
    renders joins that message. Anywhere else, the tag returns the plain static
    URL.
    """
    if email := context.get(EMAIL_CONTEXT_KEY):
        return email.attach_static(name)
    return static(name)


@register.simple_block_tag
def table(content: str, **attrs: object) -> str:
    """
    Render the block inside a layout table every client understands.

    Keyword arguments become attributes, so `{% table class="main" %}` adds a
    class next to the `role`, `border`, `cellpadding` and `cellspacing` defaults.
    """
    attributes = format_html_join("", ' {}="{}"', attrs.items())
    return format_html(
        '<table role="presentation" border="0" cellpadding="0" cellspacing="0"'
        "{}>{}</table>",
        attributes,
        content,
    )


@register.inclusion_tag("django_letter/button.html")
def button(
    href: str, value: str, disabled: bool = False, primary: bool = False
) -> dict[str, str | bool]:
    """
    Build a call-to-action link that clients render reliably.

    `primary` picks the accent colour of the bundled base template and `disabled`
    shows the label as plain text without a link.
    """
    return {
        "href": href,
        "value": value,
        "classes": "btn btn-primary" if primary else "btn",
        "disabled": disabled,
    }
