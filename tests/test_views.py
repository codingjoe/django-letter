"""Behaviour of the debug preview routes."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from django.conf import settings
from django.urls import reverse

import django_letter
from django_letter import TemplateEmail

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(
    NODE is None, reason="node is required to run the preview script"
)

STATIC = Path(django_letter.__file__).parent / "static" / "django_letter"

SCRIPT = STATIC / "preview.js"

STYLESHEET = STATIC / "basecoat.min.css"

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

# Address, whether the switch blocks, and the address to load next.
TRACKING_CASES = [
    ("http://testserver/emails/welcomeemail/", True, "/emails/welcomeemail/"),
    (
        "http://testserver/emails/welcomeemail/?raw=1&load_images=1",
        True,
        "/emails/welcomeemail/?raw=1",
    ),
    (
        "http://testserver/emails/welcomeemail/?lang=de",
        False,
        "/emails/welcomeemail/?lang=de&load_images=1",
    ),
    (
        "http://testserver/emails/welcomeemail/?load_images=1&raw=1",
        False,
        "/emails/welcomeemail/?load_images=1&raw=1",
    ),
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


def tracking_switch(content: str) -> dict[str, object]:
    tag = re.search(r'<input[^>]*\bid="block-tracking"[^>]*>', content)
    assert tag, "the preview must offer one tracking switch"
    label = re.search(
        r'<label[^>]*\bfor="block-tracking"[^>]*>(.*?)</label>', content, re.DOTALL
    )
    assert label, "the tracking switch must carry a label"
    return {
        "role": re.search(r'role="([^"]*)"', tag.group(0)).group(1),
        "checked": bool(re.search(r"\schecked(?=[\s>])", tag.group(0))),
        "label": " ".join(label.group(1).split()),
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
    # The page chrome is Basecoat, which themes through the `dark` class.
    assert 'classList.toggle("dark", theme !== "light")' in script


def test_preview_sandbox_attributes(client) -> None:
    sandbox = re.findall(r'<iframe\b[^>]*\bsandbox="([^"]*)"', preview_content(client))
    assert sandbox == [EXPECTED_SANDBOX] * 3


def preview_frames(content: str) -> list[tuple[str, str, str]]:
    """Return the class, the source and the title of every preview frame."""
    return re.findall(
        r'<iframe\b[^>]*\bclass="([^"]*)"[^>]*\bsrc="([^"]*)"[^>]*\btitle="([^"]*)"',
        content,
    )


def test_preview_frames(client) -> None:
    assert preview_frames(preview_content(client)) == [
        ("desktop", "?raw=1", "Desktop preview"),
        ("mobile", "?raw=1", "Mobile preview"),
        ("text", "?plain=1", "Plain-text preview"),
    ]


def test_preview_offers_no_raw_link(client) -> None:
    """Every body shows in a frame, so nothing opens a bare body in a tab."""
    assert 'target="_blank"' not in preview_content(client)


def test_preview_tracking_switch(client) -> None:
    content = preview_content(client)
    assert tracking_switch(content) == {
        "role": "switch",
        "checked": True,
        "label": "Block tracking",
    }
    assert content.count('src="?raw=1"') == 2


def test_preview_tracking_switch_off_loads_the_pictures(client) -> None:
    content = preview_content(client, load_images=1)
    assert tracking_switch(content) == {
        "role": "switch",
        "checked": False,
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
def test_preview_tracking_url() -> None:
    script = preview_script()
    declaration = script_declaration(script, "trackingUrl")
    program = "\n".join(
        [
            declaration,
            f"const cases = {json.dumps([case[:2] for case in TRACKING_CASES])};",
            "console.log(JSON.stringify(cases.map((c) => trackingUrl(...c))));",
        ]
    )
    results = node_json(program)
    for case, actual in zip(TRACKING_CASES, results):
        assert actual == case[2], f"trackingUrl({case[0]!r}, {case[1]}) -> {actual!r}"


@needs_node
def test_preview_script_parses() -> None:
    result = subprocess.run(
        [NODE, "--check", SCRIPT], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


def list_item(content: str, slug: str) -> str:
    match = re.search(
        rf'<a[^>]*href="{preview_url(slug)}"[^>]*>.*?</a>', content, re.DOTALL
    )
    assert match, f"the list must link the {slug} preview"
    return match.group(0)


def test_list(client) -> None:
    response = client.get(reverse("django_letter:list"))
    content = response.content.decode()
    assert response.status_code == 200
    assert content.index("invoiceemail") < content.index(
        "welcomeemail"
    )  # sorted by slug
    for slug, name, template in [
        ("invoiceemail", "InvoiceEmail", "testapp/invoice.html"),
        ("logoemail", "LogoEmail", "testapp/logo.html"),
        ("remoteimagesemail", "RemoteImagesEmail", "testapp/remote.html"),
        ("retinalogoemail", "RetinaLogoEmail", "testapp/retina.html"),
        ("welcomeemail", "WelcomeEmail", "testapp/welcome.html"),
    ]:
        item = list_item(content, slug)
        # Each entry is a Basecoat item that shows where the class and its
        # template live.
        assert 'class="item"' in item
        assert f"<h2>{name}</h2>" in item
        assert "<code>tests.testapp.emails</code>" in item
        assert f"<code>{template}</code>" in item


def test_list_keeps_the_link_and_list_roles(client) -> None:
    """A list item around the link, so neither role replaces the other."""
    content = client.get(reverse("django_letter:list")).content.decode()
    assert '<ul class="item-group" role="list">' in content
    assert re.search(
        r'<li>\s*<a\b[^>]*class="item"[^>]*>\s*<figure', content, re.DOTALL
    )
    assert 'role="listitem"' not in content


def test_list_ships_the_basecoat_stylesheet(client) -> None:
    content = client.get(reverse("django_letter:list")).content.decode()
    assert 'href="/static/django_letter/basecoat.min.css"' in content
    css = STYLESHEET.read_text()
    assert ".item-group" in css
    assert "basecoat-css@1.0.2" in css  # the vendored version of the banner


def test_list_without_emails(client, monkeypatch) -> None:
    monkeypatch.setattr(TemplateEmail, "get_email_classes", classmethod(lambda cls: {}))
    content = client.get(reverse("django_letter:list")).content.decode()
    assert 'class="empty"' in content
    assert "No emails discovered yet" in content


def test_preview(client) -> None:
    url = preview_url("welcomeemail")
    response = client.get(url)
    content = response.content.decode()
    assert response.status_code == 200
    assert '<nav class="breadcrumb" aria-label="Breadcrumb">' in content
    assert f'<a href="{reverse("django_letter:list")}">All emails</a>' in content
    assert '<span aria-current="page">WelcomeEmail</span>' in content
    assert 'src="?raw=1"' in content
    assert 'src="?plain=1"' in content


def test_preview_ships_the_basecoat_chrome(client) -> None:
    content = client.get(preview_url("welcomeemail")).content.decode()
    assert 'href="/static/django_letter/basecoat.min.css"' in content
    assert 'class="breadcrumb"' in content
    assert 'class="field"' in content
    assert 'role="switch"' in content


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
    assert 'src="?lang=de&amp;raw=1"' in page.content.decode()
    assert 'src="?lang=de&amp;plain=1"' in page.content.decode()


def language_trigger(content: str) -> str:
    """Return the label of the button that opens the language palette."""
    match = re.search(
        r'<button\b[^>]*\bid="language-trigger"[^>]*>(.*?)</button>', content, re.DOTALL
    )
    assert match, "the preview must offer one language trigger"
    return " ".join(re.sub(r"<[^>]+>", " ", match.group(1)).split())


def language_menu(content: str) -> dict[str, tuple[str, bool]]:
    """Return the name and the selection of every entry, keyed by its code."""
    assert 'class="command-dialog"' in content, "the palette must be a command"
    entries = {}
    for tag, body in re.findall(
        r'(<a\b[^>]*\brole="menuitem"[^>]*>)(.*?)</a>', content, re.DOTALL
    ):
        code = re.search(r'\blang=([^"&]+)"', tag).group(1)
        name = re.search(r"<span>([^<]+)</span>", body).group(1)
        entries[code] = (name, 'aria-selected="true"' in tag)
    return entries


def test_preview_language_switcher(client) -> None:
    content = preview_content(client)
    assert 'src="?raw=1"' in content

    assert language_trigger(content) == "English"

    menu = language_menu(content)
    assert len(menu) == len(settings.LANGUAGES)
    assert menu["de"] == ("German", False)
    assert menu["en"] == ("English", True)
    assert 'data-keywords="de"' in content
    assert 'data-empty="No language found."' in content


def test_preview_language_switcher_marks_the_language_in_the_address(
    client, settings
) -> None:
    settings.LANGUAGES = [("en", "English"), ("de", "Deutsch")]
    content = client.get(preview_url("welcomeemail"), {"lang": "de"}).content.decode()
    assert language_trigger(content) == "Deutsch"
    assert language_menu(content)["de"] == ("Deutsch", True)


def test_preview_language_switcher_keeps_the_downloads_stopped(
    client, settings
) -> None:
    """A language joins the choice of the switch, so it stays in the address."""
    settings.LANGUAGES = [("en", "English"), ("de", "Deutsch")]
    content = preview_content(client, load_images=1)
    assert 'href="?load_images=1&amp;lang=de"' in content


def test_preview_language_switcher_needs_a_choice(client, settings) -> None:
    settings.LANGUAGES = [("en", "English")]
    assert 'id="language-trigger"' not in preview_content(client)
    assert 'id="language-dialog"' not in preview_content(client)

    settings.LANGUAGES = [("en", "English"), ("de", "Deutsch")]
    settings.USE_I18N = False
    assert 'id="language-trigger"' not in preview_content(client)


def test_preview_language_switcher_without_a_configured_language(
    client, settings
) -> None:
    """A code outside `LANGUAGES` still renders, it just picks no entry."""
    settings.LANGUAGES = [("en", "English"), ("de", "Deutsch")]
    content = client.get(preview_url("welcomeemail"), {"lang": "xx"}).content.decode()
    assert language_trigger(content) == "xx"
    assert not any(selected for _, selected in language_menu(content).values())


def test_preview_ships_the_basecoat_scripts(client) -> None:
    content = preview_content(client)
    scripts = re.findall(r'<script[^>]*\bsrc="([^"]+)"', content)
    assert scripts == [
        "/static/django_letter/basecoat.min.js",
        "/static/django_letter/command.min.js",
        "/static/django_letter/preview.js",
    ]
    for name in ("basecoat.min.js", "command.min.js"):
        asset = (STATIC / name).read_text()
        assert "basecoat-css@1.0.2" in asset


def test_preview_script_wires_the_language_palette() -> None:
    declaration = script_declaration(preview_script(), "wireLanguagePalette")
    assert "dialog.showModal()" in declaration
    assert "dialog.close()" in declaration


@needs_node
def test_preview_vendored_scripts_parse() -> None:
    for name in ("basecoat.min.js", "command.min.js"):
        result = subprocess.run(
            [NODE, "--check", STATIC / name],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr


def test_preview_unknown_slug(client) -> None:
    response = client.get(preview_url("unknown"))
    assert response.status_code == 404
