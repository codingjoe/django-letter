"""Behaviour of the bundled `django_mail` template tags."""

from django.template import Context, Template
from django.template.loader import render_to_string

TABLE = '<table role="presentation" border="0" cellpadding="0" cellspacing="0"'


def render(source: str, **context: object) -> str:
    """Render a snippet with the `django_mail` library loaded."""
    return Template("{% load django_mail %}" + source).render(Context(context))


def test_table_without_attributes() -> None:
    assert render("{% table %}content{% endtable %}") == f"{TABLE}>content</table>"


def test_table_renders_attributes() -> None:
    html = render('{% table class="main" %}content{% endtable %}')
    assert html == f'{TABLE} class="main">content</table>'


def test_table_renders_attribute_from_context() -> None:
    html = render("{% table class=classes %}content{% endtable %}", classes="main")
    assert html == f'{TABLE} class="main">content</table>'


def test_table_escapes_attribute_values() -> None:
    html = render(
        "{% table class=classes %}content{% endtable %}",
        classes='main" onload="alert(1)',
    )
    assert html == f'{TABLE} class="main&quot; onload=&quot;alert(1)">content</table>'


def test_button_renders_table_classes() -> None:
    primary = render('{% button href="/confirm" value="Confirm" primary=True %}')
    assert f'{TABLE} class="btn btn-primary">' in primary
    plain = render('{% button href="/later" value="Later" %}')
    assert f'{TABLE} class="btn">' in plain


def test_base_template_renders_tables() -> None:
    html = render_to_string("django_mail/base.html")
    assert f'{TABLE} class="body">' in html
    assert f'{TABLE} class="main">' in html
    assert f"{TABLE}>" in html
