<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://github.com/codingjoe/django-letter/raw/main/docs/images/logo-dark.svg">
    <source media="(prefers-color-scheme: light)" srcset="https://github.com/codingjoe/django-letter/raw/main/docs/images/logo-light.svg">
    <img alt="django-letter: HTML emails via Django templates." src="https://github.com/codingjoe/django-letter/raw/main/docs/images/logo-light.svg">
  </picture>
<br>
  <a href="https://github.com/codingjoe/django-letter/issues/new/choose">Issues</a> |
  <a href="https://github.com/codingjoe/django-letter/releases">Changelog</a> |
  <a href="https://github.com/sponsors/codingjoe">Funding</a> 💚
</p>

# django-letter [![PyPi Version](https://img.shields.io/pypi/v/django-letter.svg)](https://pypi.python.org/pypi/django-letter/) [![Test Coverage](https://codecov.io/gh/codingjoe/django-letter/branch/main/graph/badge.svg)](https://codecov.io/gh/codingjoe/django-letter) [![GitHub License](https://img.shields.io/github/license/codingjoe/django-letter)](https://raw.githubusercontent.com/codingjoe/django-letter/main/LICENSE)

**Write an email once as a Django template. Send it as HTML with inlined CSS and a plain-text alternative.**

django-letter renders your markup, inlines the CSS, and derives a Gmail-style
plain-text body from the same template.

## Setup

1. Add the package:

   ```console
   uv add django-letter
   ```

1. Add the app to your settings:

   ```python
   # settings.py
   INSTALLED_APPS = [
       "django_letter",
       # ...
   ]
   ```

1. Add an `emails.py` module to each app that sends mail. Put it next to that
   app's `views.py`.

1. Mount the debug pages in your root URLconf:

   ```python
   # urls.py
   from django.urls import include, path

   urlpatterns = [
       path("emails/", include("django_letter.urls")),
   ]
   ```

   While `DEBUG` is true, you can preview each email at `/emails/`:

   ![WelcomeEmail in the desktop frame and the mobile frame of the preview page](https://github.com/codingjoe/django-letter/raw/main/docs/images/preview.png)

## Usage

### Make a pretty email

Subclass `TemplateEmail`. Set `template_name`, `subject`, and the values your
markup needs. This example attaches the invoice and adds a tracking button:

```python
# myapp/emails.py
from django.utils.translation import gettext_lazy as _

from django_letter import TemplateEmail


class OrderShippedEmail(TemplateEmail):
    template_name = "emails/order_shipped.html"
    subject = _("Order %(number)s has shipped")
    preheader = _("Track your parcel with the link inside.")

    def __init__(self, order, **kwargs):
        self.order = order
        super().__init__(**kwargs)

    def get_context_data(self):
        return {"order": self.order, "number": self.order.number}

    def gen_attachments(self):
        yield "invoice.pdf", self.order.invoice, "application/pdf"
```

`subject` and `preheader` fill their `%(name)s` placeholders from the context of
the template. Write `%%` for a literal percent sign. `gen_attachments()` yields
`(filename, content, MIME type)` tuples. Use `None` as the MIME type and Python
guesses it from the file name.

The template extends the bundled base template and fills the `content` block:

```django
{# myapp/templates/emails/order_shipped.html #}
{% extends "django_letter/base.html" %}
{% load django_letter %}

{% block content %}
  <h1>Thanks for your order</h1>
  <p>Order {{ number }} is on its way.</p>
  {% button href=order.tracking_url value="Track parcel" primary=True %}
  {% table class="summary" %}
    <tr>
      <td>Invoice</td>
      <td>{{ number }}</td>
    </tr>
  {% endtable %}
{% endblock content %}
```

`{% button %}` builds a table that Outlook keeps intact, with the link in a new
tab. `primary` uses the accent color of the base template. `disabled` shows the
label as plain text without a link.

`{% table %}` wraps the rows in a layout table that every email client
understands. Each keyword argument becomes an attribute. The tag adds
`role="presentation"`, `border="0"`, `cellpadding="0"` and `cellspacing="0"`, and
it escapes each attribute value.

The base template keeps the layout safe for email clients and inlines the CSS
when the message is built. It writes `subject` into `<title>` and `preheader`
into a hidden span. Its blocks are `container`, `logo`, `content`, `footer` and
`footer_content`. Its classes cover the layout (`container`, `content`, `main`,
`wrapper`, `footer`, `content-block`), alignment (`align-left`, `align-right`,
`align-center`) and spacing (`first`, `last`, `mt0`, `mb0`).

Add your own `<style>` rules in the `extra_header` block. The package inlines
them:

```django
{% block extra_header %}
  <style>
    .brand {
      color: #bada55;
    }
  </style>
{% endblock extra_header %}
```

```python
OrderShippedEmail(order, to=["customer@example.com"], language="de").send()
OrderShippedEmail.to_user(user, order=order, language="de").send()
```

### Test it

Render the email in your tests without a mail backend:

```python
def test_order_shipped():
    email = OrderShippedEmail.render_preview(order=order)

    assert "Order A-1 is on its way" in email.html
    assert "Track parcel <https://example.com/track/A-1>" in email.body
```

`render_preview()` returns the rendered email. It takes the constructor
arguments of the class. `context=` merges extra values over
`get_context_data()`. `language=` picks the language. The email carries `html`,
`body`, `subject` and `attachments`.

## Sponsors

[![Sponsors](https://django.the-box.sh/sponsors/codingjoe/django-letter.svg)](https://github.com/sponsors/codingjoe)
