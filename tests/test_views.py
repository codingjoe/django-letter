"""Behaviour of the debug preview routes."""

from django.urls import reverse


def preview_url(slug: str) -> str:
    return reverse("django_mail:preview", kwargs={"slug": slug})


def test_list(client) -> None:
    response = client.get(reverse("django_mail:list"))
    content = response.content.decode()
    assert response.status_code == 200
    assert content.index("invoiceemail") < content.index(
        "welcomeemail"
    )  # sorted by slug
    for slug, name in [
        ("invoiceemail", "InvoiceEmail"),
        ("welcomeemail", "WelcomeEmail"),
    ]:
        assert f'{preview_url(slug)}">{name}</a>' in content


def test_preview(client) -> None:
    url = preview_url("welcomeemail")
    response = client.get(url)
    content = response.content.decode()
    assert response.status_code == 200
    assert "<strong>WelcomeEmail</strong>" in content
    assert 'src="?raw=1"' in content
    assert 'href="?plain=1"' in content


def test_preview_raw(client) -> None:
    response = client.get(preview_url("welcomeemail"), {"raw": "1"})
    assert response.status_code == 200
    assert response["Content-Type"] == "text/html; charset=utf-8"
    assert "background-color:#0867ec" in response.content.decode()


def test_preview_plain(client) -> None:
    response = client.get(preview_url("welcomeemail"), {"plain": "1"})
    assert response.status_code == 200
    assert response["Content-Type"] == "text/plain; charset=utf-8"
    assert (
        "Confirm address <http://testserver/welcome/confirm>"
        in response.content.decode()
    )


def test_preview_language(client) -> None:
    url = preview_url("welcomeemail")
    raw = client.get(url, {"lang": "de", "raw": "1"})
    assert raw.status_code == 200
    assert '<html lang="de">' in raw.content.decode()

    page = client.get(url, {"lang": "de"})
    assert 'href="?lang=de&amp;raw=1"' in page.content.decode()


def test_preview_unknown_slug(client) -> None:
    response = client.get(preview_url("unknown"))
    assert response.status_code == 404
