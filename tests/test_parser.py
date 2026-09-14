"""Behaviour of the HTML-to-text flattening."""

import pytest

from django_mail.parser import html_to_text


@pytest.mark.parametrize(
    ("html", "expected"),
    [
        pytest.param("", "", id="empty"),
        pytest.param("unwrapped text", "", id="text-without-elements-is-dropped"),
        pytest.param("<p>Hello</p>", "Hello", id="paragraph"),
        pytest.param(
            "<div><p>Hello</p><p>World</p></div>",
            "Hello\n\nWorld",
            id="div-with-paragraphs",
        ),
        pytest.param("<table><tr><td>Cell</td></tr></table>", "Cell", id="table"),
        pytest.param("<h1>Hello</h1>", "Hello", id="heading"),
        pytest.param("<p>Hello<br>World</p>", "Hello\nWorld", id="line-break"),
        pytest.param(
            "<p>Hello<br><br><br>World</p>",
            "Hello\n\nWorld",
            id="line-break-run-collapses",
        ),
        pytest.param("<div><hr></div>", "-" * 50, id="horizontal-rule"),
        pytest.param(
            '<p><a href="https://example.com">Example</a></p>',
            "Example <https://example.com>",
            id="link",
        ),
        pytest.param("<p><a>Example</a></p>", "Example", id="link-without-href"),
        pytest.param('<p><a href="https://example.com"></a></p>', "", id="empty-link"),
        pytest.param(
            "<p><strong>bold</strong> <em>italic</em> <b>b</b> <i>i</i> <u>u</u> <code>c</code></p>",
            "*bold* *italic* *b* *i* *u* *c*",
            id="emphasis",
        ),
        pytest.param(
            '<div><img src="logo.png" alt="Logo"></div>',
            "[image: Logo]",
            id="image",
        ),
        pytest.param('<div><img src="logo.png"></div>', "", id="image-without-alt"),
        pytest.param(
            "<div><title>Subject</title><style>p {}</style><script>x()</script><p>Body</p></div>",
            "Body",
            id="head-elements-are-dropped",
        ),
        pytest.param("<div>Unclosed", "Unclosed", id="unclosed-element"),
        pytest.param("Hello</p>", "", id="stray-end-tag"),
        pytest.param(
            "<p>  Hello   World  </p>", "Hello World", id="whitespace-collapses"
        ),
        pytest.param("<p>\ufeffHello</p>", "Hello", id="byte-order-mark"),
    ],
)
def test_html_to_text(html: str, expected: str) -> None:
    assert html_to_text(html) == expected
