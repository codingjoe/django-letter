"""Behaviour of the debug preview routes."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from django.urls import reverse

import django_letter

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(
    NODE is None, reason="node is required to run the preview script"
)

SCRIPT = Path(django_letter.__file__).parent / "static" / "django_letter" / "preview.js"

EXPECTED_SANDBOX = "allow-same-origin"

EXPECTED_INVERT_CSS = "img, video, svg { filter: invert(1) hue-rotate(180deg) }"

# Values read back from a browser as `MediaList.mediaText`.
FORCE_SCHEME_CASES = [
    ("(prefers-color-scheme: dark), (max-width: 600px)", "light", "(max-width: 600px)"),
    ("(prefers-color-scheme: dark), (max-width: 600px)", "dark", "all"),
    (
        "screen and (min-width: 100px) and (prefers-color-scheme: dark)",
        "dark",
        "screen and (min-width: 100px)",
    ),
    (
        "screen and (min-width: 100px) and (prefers-color-scheme: dark)",
        "light",
        "not all",
    ),
    ("(prefers-color-scheme: dark)", "dark", "all"),
    ("(prefers-color-scheme: dark)", "light", "not all"),
    ("(prefers-color-scheme: light), (prefers-color-scheme: dark)", "light", "all"),
]


def preview_url(slug: str) -> str:
    return reverse("django_letter:preview", kwargs={"slug": slug})


def preview_content(client, **params) -> str:
    return client.get(preview_url("welcomeemail"), params).content.decode()


def preview_script() -> str:
    return SCRIPT.read_text()


def declared_rules(content: str) -> dict[str, set[str]]:
    style = re.sub(
        r"/\*.*?\*/",
        "",
        "".join(re.findall(r"<style>(.*?)</style>", content, re.DOTALL)),
        flags=re.DOTALL,
    )
    return {
        " ".join(selector.replace("'", '"').split()): {
            " ".join(declaration.split())
            for declaration in body.split(";")
            if declaration.strip()
        }
        for selector, body in re.findall(r"([^{}]*)\{([^}]*)\}", style)
    }


def script_declaration(script: str, name: str) -> str:
    start = script.find(f"function {name}(")
    if start == -1:
        start = script.find(f"const {name} =")
    assert start != -1, f"{name} is missing from the preview script"
    depth = 0
    for end, character in enumerate(script[start:], start):
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return script[start : end + 1]
    pytest.fail(f"{name} is unterminated")


def content_policy(response) -> dict[str, list[str]]:
    policy = {}
    for directive in response["Content-Security-Policy"].split(";"):
        name, _, tokens = directive.strip().partition(" ")
        policy[name] = tokens.split()
    return policy


def image_switch(content: str) -> dict[str, str]:
    match = re.search(r'<a[^>]*\brole="switch"[^>]*>.*?</a>', content, re.DOTALL)
    assert match, "the preview must offer one images switch"
    opening = match.group(0)[: match.group(0).index(">")]
    return {
        "href": re.search(r'href="([^"]*)"', opening).group(1),
        "checked": re.search(r'aria-checked="([^"]*)"', opening).group(1),
        "label": " ".join(re.sub(r"<[^>]*>", " ", match.group(0)).split()),
    }


def node_json(program: str) -> object:
    result = subprocess.run(
        [NODE, "-e", program], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_preview_theme_toggle(client) -> None:
    content = preview_content(client)
    script = preview_script()

    values = re.findall(r'<input type="radio" name="theme" value="([^"]+)">', content)
    assert values == ["light", "invert", "author"]

    assert content.index('src="/static/django_letter/preview.js"') < content.index(
        "<style>"
    )

    assert 'data-theme="light"' in content

    stored = re.search(r"(\[[^\]]+\])\.includes\(stored\)", script)
    assert stored, "the preview script must restore a stored theme"
    assert json.loads(stored.group(1)) == values

    assert 'const KEY = "django-letter:preview-theme"' in script
    assert "localStorage.getItem(KEY)" in script
    assert "localStorage.setItem(KEY" in script


def test_preview_sandbox_attributes(client) -> None:
    sandbox = re.findall(r'<iframe\b[^>]*\bsandbox="([^"]*)"', preview_content(client))
    assert sandbox == [EXPECTED_SANDBOX, EXPECTED_SANDBOX]


def test_preview_html_link_has_no_opener(client) -> None:
    link = re.search(r"<a\b[^>]*>HTML</a>", preview_content(client))
    assert link, "the preview must offer one HTML link"
    assert re.search(r'\brel="noopener"', link.group(0))


def test_preview_images_switch(client) -> None:
    content = preview_content(client)
    assert image_switch(content) == {
        "href": "?load_images=1",
        "checked": "true",
        "label": "Block tracking",
    }
    assert content.count('src="?raw=1"') == 2


def test_preview_images_switch_off_loads_the_pictures(client) -> None:
    content = preview_content(client, load_images=1)
    assert image_switch(content) == {
        "href": "?",
        "checked": "false",
        "label": "Block tracking",
    }
    assert content.count('src="?load_images=1&amp;raw=1"') == 2


def test_preview_invert_css() -> None:
    match = re.search(r"const INVERT_CSS\s*=\s*(.*?);", preview_script(), re.DOTALL)
    assert match, "the preview page must define INVERT_CSS"
    css = " ".join("".join(re.findall(r'"([^"]*)"', match.group(1))).split())
    assert css == EXPECTED_INVERT_CSS


def test_preview_forces_the_frame_scheme() -> None:
    """The message follows the system scheme, so the frame's scheme is forced."""
    declaration = script_declaration(preview_script(), "applyScheme")
    assert "doc.documentElement.style.colorScheme = scheme;" in declaration


def test_preview_invert_frame_rule(client) -> None:
    rules = declared_rules(preview_content(client))
    assert rules.get('html[data-theme="invert"] iframe') == {
        "filter: invert(1) hue-rotate(180deg)",
        "border-color: #e5e7eb",
        "background-color: #ffffff",
    }


@needs_node
def test_preview_email_scheme_table() -> None:
    declaration = script_declaration(preview_script(), "EMAIL_SCHEME")
    scheme = node_json(f"{declaration};\nconsole.log(JSON.stringify(EMAIL_SCHEME));")
    assert scheme == {"light": "light", "invert": "light", "author": "dark"}


@needs_node
def test_preview_force_scheme() -> None:
    script = preview_script()
    preference = re.search(r"const PREFERENCE\s*=\s*.*?;", script)
    assert preference, "the preview script must define PREFERENCE"
    program = "\n".join(
        [
            preference.group(0),
            script_declaration(script, "forceScheme"),
            f"const cases = {json.dumps([case[:2] for case in FORCE_SCHEME_CASES])};",
            "console.log(JSON.stringify(cases.map((c) => forceScheme(...c))));",
        ]
    )
    results = node_json(program)
    for case, actual in zip(FORCE_SCHEME_CASES, results):
        assert actual == case[2], f"forceScheme({case[0]!r}, {case[1]!r}) -> {actual!r}"


@needs_node
def test_preview_script_parses() -> None:
    result = subprocess.run(
        [NODE, "--check", SCRIPT], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


def test_list(client) -> None:
    response = client.get(reverse("django_letter:list"))
    content = response.content.decode()
    assert response.status_code == 200
    assert content.index("invoiceemail") < content.index(
        "welcomeemail"
    )  # sorted by slug
    for slug, name in [
        ("invoiceemail", "InvoiceEmail"),
        ("logoemail", "LogoEmail"),
        ("remoteimagesemail", "RemoteImagesEmail"),
        ("retinalogoemail", "RetinaLogoEmail"),
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


@pytest.mark.parametrize("params", [{"raw": "1"}, {"raw": "1", "load_images": "1"}])
def test_preview_raw_stays_inert_when_opened_alone(client, params) -> None:
    policy = content_policy(client.get(preview_url("welcomeemail"), params))
    assert "allow-same-origin" in policy["sandbox"]
    assert "allow-scripts" not in policy["sandbox"]
    assert policy["script-src"] == ["'none'"]


def test_preview_raw_points_pictures_at_the_static_url(client) -> None:
    params = {"raw": "1", "load_images": "1"}
    content = client.get(preview_url("logoemail"), params).content.decode()
    assert 'src="/static/testapp/logo.png"' in content
    assert "cid:" not in content

    content = client.get(preview_url("retinalogoemail"), params).content.decode()
    assert 'src="/static/testapp/logo.png"' in content
    # `static()` percent-encodes the `@` of the retina name, so a picture that
    # had its shorter sibling replaced first would still carry a plain `@2x`.
    assert 'src="/static/testapp/logo.png%402x.png"' in content
    assert "cid:" not in content


def test_preview_raw_resolves_relative_sources_from_the_origin(client) -> None:
    """A relative source resolves from the site root, not the preview path."""
    content = client.get(preview_url("invoiceemail"), {"raw": "1"}).content.decode()
    assert 'src="http://testserver/img/hero.png"' in content
    assert "/emails/invoiceemail/img/hero.png" not in content


def test_preview_raw_blocks_every_download(client) -> None:
    response = client.get(preview_url("remoteimagesemail"), {"raw": "1"})
    # A `{% static %}` picture is a download like any other, so no origin is allowed.
    assert content_policy(response)["img-src"] == ["data:"]
    content = response.content.decode()
    # The carried picture travels inside, the way a client embeds it.
    assert 'src="data:image/png;base64,' in content
    assert 'src="http://testserver/static/testapp/logo.png"' in content
    assert 'src="https://placehold.co/480x160.png"' in content


def test_preview_raw_loads_when_asked(client) -> None:
    response = client.get(
        preview_url("remoteimagesemail"), {"raw": "1", "load_images": "1"}
    )
    assert "img-src" not in content_policy(response)
    assert 'src="/static/testapp/logo.png"' in response.content.decode()
    assert "data:image/png" not in response.content.decode()


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
