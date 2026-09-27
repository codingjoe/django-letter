import re

import pytest
from django.urls import reverse

from tests.testapp.emails import WelcomeEmail

DARK_QUERY = "@media (prefers-color-scheme: dark)"

EXPECTED_DARK_RULES = {
    "body, .body": {"background-color: #0b1120 !important"},
    "body": {"color: #e5e7eb !important"},
    ".main": {
        "border-color: #334155 !important",
        "background-color: #1f2937 !important",
    },
    "a, .text-link": {"color: #93c5fd !important"},
    ".footer td, .footer p, .footer span, .footer a": {
        "color: #9ca3af !important",
    },
    ".btn table td": {"background-color: #1f2937 !important"},
    ".btn a": {
        "border-color: #93c5fd !important",
        "background-color: #1f2937 !important",
        "color: #93c5fd !important",
    },
    ".btn-primary table td": {"background-color: #0867ec !important"},
    ".btn-primary a": {
        "border-color: #0867ec !important",
        "background-color: #0867ec !important",
        "color: #fff !important",
    },
}


def rendered() -> str:
    email = WelcomeEmail(name="Ada", language="en", base_url="http://example.com")
    return email.render_html(name="Ada")


def dark_block(html: str) -> str:
    start = html.index("{", html.index(DARK_QUERY))
    depth = 0
    for end, character in enumerate(html[start:], start):
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return html[start + 1 : end]
    pytest.fail("the dark media query is unterminated")


def dark_rules(html: str) -> dict[str, set[str]]:
    return {
        " ".join(selector.split()): {
            " ".join(declaration.split())
            for declaration in body.split(";")
            if declaration.strip()
        }
        for selector, body in re.findall(r"([^{}]*)\{([^}]*)\}", dark_block(html))
    }


def test_email_declares_the_scheme() -> None:
    html = rendered()
    assert '<meta name="color-scheme" content="light dark">' in html
    assert '<meta name="supported-color-schemes" content="light dark">' in html


def test_light_styles_are_inlined() -> None:
    assert "background-color:#f4f5f6" in rendered()


def test_dark_styles_survive_inlining() -> None:
    assert dark_rules(rendered()) == EXPECTED_DARK_RULES


def test_list_page_follows_the_scheme(client) -> None:
    content = client.get(reverse("django_letter:list")).content.decode()
    assert "color-scheme: light dark" in content
    assert "(prefers-color-scheme: dark)" in content
