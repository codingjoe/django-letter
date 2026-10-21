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

   While `DEBUG` is true, `/emails/` lists every discovered email with the
   module of its class and its template, and previews each one:

   <picture>
     <source media="(prefers-color-scheme: dark)" srcset="https://github.com/codingjoe/django-letter/raw/main/docs/images/preview-dark.png">
     <source media="(prefers-color-scheme: light)" srcset="https://github.com/codingjoe/django-letter/raw/main/docs/images/preview-light.png">
     <img alt="WelcomeEmail in the desktop, mobile and plain-text frames of the preview page" src="https://github.com/codingjoe/django-letter/raw/main/docs/images/preview-light.png">
   </picture>

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

Write `{% attached_static %}` where the markup needs a picture. It takes the
same path as `{% static %}`, and the message carries the file with it:

```django
{# myapp/templates/emails/newsletter.html #}
{% extends "django_letter/base.html" %}
{% load django_letter %}

{% block content %}
  <img src="{% attached_static 'images/logo.png' %}" alt="Logo">
{% endblock content %}
```

The same tag works in your web views and in the debug pages, where it
returns the plain static URL.

The `OrderShippedEmail` template extends the bundled base template and fills the
`content` block:

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

### Let recipients manage preferences

Notifications are optional. Add the subapp only when you send recurring mail
and recipients may want to control what arrives:

```python
# settings.py
INSTALLED_APPS = [
    "django_letter",
    "django_letter.notifications",
    # ...
]
```

The core app renders and sends mail without this entry. The subapp adds
`NotificationPreference` and its migration. Run `migrate` after you add it:

```console
uv run manage.py migrate
```

Define each kind of email once and decorate the class that sends it:

```python
# myapp/emails.py
from django.utils.translation import gettext_lazy as _

from django_letter import TemplateEmail
from django_letter.notifications import Notification, subscribe

WEEKLY_DIGEST = Notification(
    "weekly-digest",
    _("Weekly digest"),
    _("A weekly summary of your account."),
    default=True,
)
PRODUCT_NEWS = Notification(
    "product-news",
    _("Product news"),
    _("Occasional updates about new features."),
    default=False,
)


@subscribe(WEEKLY_DIGEST)
class WeeklyDigestEmail(TemplateEmail):
    template_name = "emails/weekly_digest.html"
    subject = _("Your weekly digest")
    preheader = _("A summary of your account this week.")

    def __init__(self, account, **kwargs):
        self.account = account
        super().__init__(**kwargs)

    def get_context_data(self):
        return {"account": self.account, "items": self.account.recent_items()}
```

The slug of a `Notification` must be 100 characters or fewer and must equal
its own `slugify()` output. That allows lower-case ASCII letters, digits,
hyphens, and underscores. A slug registers once. A bad or duplicate slug
raises `NotificationImproperlyConfigured`.

Mount both views under a public path:

```python
# urls.py
from django.urls import include, path

urlpatterns = [
    path("notifications/", include("django_letter.notifications.urls")),
]
```

A decorated message adds up to three values to the template context. It may
name zero or one distinct recipient across `to`, `cc`, and `bcc`. With one, it
adds both links. With none, it renders without them. The values are:

- `unsubscribe_url`: signed link to a confirmation page. The page disables this
  notification for that recipient only after a POST, so a scanner that opens
  the link changes nothing.
- `manage_notifications_url`: signed link to the preferences form for that
  recipient.
- `notification`: the `Notification` object itself. It is not tied to an
  address.

Put the first one in the footer:

```django
{# myapp/templates/emails/weekly_digest.html #}
{% extends "django_letter/base.html" %}
{% load i18n %}

{% block content %}
  <h1>{% translate "This week" %}</h1>
  <ul>
    {% for item in items %}<li>{{ item }}</li>{% endfor %}
  </ul>
{% endblock content %}

{% block footer_content %}
  {% if unsubscribe_url %}
    <p>
      {% translate "You get this email because you subscribed to the weekly digest." %}
      <a href="{{ unsubscribe_url }}">{% translate "Unsubscribe" %}</a>
    </p>
  {% endif %}
{% endblock footer_content %}
```

The message carries the one-click headers as well. A mail client posts to the
same confirmation link, and the POST disables the notification:

```text
List-Unsubscribe: <https://example.com/notifications/<token>/weekly-digest/unsubscribe/>
List-Unsubscribe-Post: List-Unsubscribe=One-Click
```

`send()` returns `0` without delivering when the message names no recipient or
when the recipient's preference is off. A decorated message may name zero or
one distinct recipient across `to`, `cc`, and `bcc`. With more, both rendering
and sending raise `EmailImproperlyConfigured`, because one token cannot stand
for several addresses.

The manage view renders the package form template
`django_letter_notifications/notification_form.html`, with one checkbox per
registered notification. Each box starts from its `default` and the stored
overrides. To render and save the same preferences in your own view:

```python
from django.shortcuts import render

from django_letter.notifications.forms import NotificationForm


def notification_settings(request):
    form = NotificationForm(
        email=request.user.email,
        data=request.POST or None,
    )
    if form.is_valid():
        form.save()
    return render(request, "notifications/settings.html", {"form": form})
```

Reuse that template in your own view, or copy it to change the layout. It
expects `form`, and the optional `saved` flag shows the confirmation line.

The form needs bound data, so pass `request.POST or None`. An unbound form
never validates.

A signed link carries the digest instead of the address. `hash_email()` from
`django_letter.notifications` returns a 64-character hex SHA-256 digest of the
trimmed, lower-cased address, keyed with `settings.SECRET_KEY`. Pass
`email_hash=hash_email("ada@example.com")` in place of `email`. The link token
comes from `sign_email_hash()`, and `unsign_email_hash()` returns the digest
again. Both signing helpers are exported from `django_letter.notifications`.
`unsign_email_hash()` raises `BadSignature` from `django.core.signing` when the
token was altered or signed with another salt. Check or change a preference in
code:

```python
if WEEKLY_DIGEST.is_enabled("ada@example.com"):
    WeeklyDigestEmail.to_user(user, account=account, language="en").send()

WEEKLY_DIGEST.set_enabled("ada@example.com", False)
```

The subapp must be installed for these calls. Without it, they raise
`NotificationImproperlyConfigured` and name the missing entry.

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

### Print the emails to your shell

Point Django at the console backend while you develop, and keep it behind
`DEBUG` so production still sends real mail:

```python
# settings.py
if DEBUG:
    MAILERS = {"default": {"BACKEND": "django_letter.backends.ConsoleEmailBackend"}}
```

The message headers and the plain-text body reach the shell. The HTML
alternative and the attachments stay out, and a line below the separator counts
what was left out:

```console
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="===============7264214045523647149=="
Subject: Invoice 2025-001
From: billing@example.com
To: ada@example.com
Date: Tue, 15 Sep 2026 16:46:14 +0000
Message-ID: <178949077460.48066.7983759548031159413@example.com>

--===============7264214045523647149==
Content-Type: text/plain; charset="utf-8"
Content-Transfer-Encoding: 7bit

Payment is due by 1 June. Invoice 2025-001

Payment is due by 1 June. The payment terms are attached.

--===============7264214045523647149==--

-------------------------------------------------------------------------------
2 more part(s) have been omitted.
```

## Sponsors

[![Sponsors](https://django.the-box.sh/sponsors/codingjoe/django-letter.svg)](https://github.com/sponsors/codingjoe)
