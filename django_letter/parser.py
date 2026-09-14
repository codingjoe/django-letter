from __future__ import annotations

import dataclasses
import re
from html.parser import HTMLParser

__all__ = ["HTML2TextParser", "Node", "html_to_text"]


@dataclasses.dataclass
class Node:
    name: str
    attrs: dict[str, str | None]
    parent: Node | None
    children: list[Node | str] = dataclasses.field(init=False, default_factory=list)

    def __post_init__(self) -> None:
        if self.parent:
            self.parent.children.append(self)

    def __str__(self) -> str:
        match self.name:
            case "br":
                return "\n"
            case "hr":
                return f"\n{'-' * 50}\n"
            case "a":
                href = self.attrs.get("href")
                return f"{self.text} <{href}>" if href and self.text else self.text
            case "p" | "h1" | "h2" | "h3" | "h4" | "h5" | "h6" | "table" | "tr" | "div":
                return f"{self.text}\n\n"
            case "em" | "strong" | "i" | "b" | "u" | "code":
                return f"*{self.text}*"
            case "img":
                if alt := self.attrs.get("alt"):
                    return f"[image: {alt}]"
            case "script" | "style" | "title":
                return ""
        return f"{self.text}"

    @property
    def text(self) -> str:
        return "".join(
            " ".join(child.split("\n")) if isinstance(child, str) else str(child)
            for child in self.children
        )


class HTML2TextParser(HTMLParser):
    """
    Flatten markup into a plain-text body the way Gmail does.

    Links keep their target in angle brackets, images their alt text, and
    emphasis asterisks; unclosed elements and stray end tags are tolerated.
    """

    DOUBLE_NEWLINE = re.compile(r"\n{3,}")  # 3 or more newlines
    DOUBLE_SPACE = re.compile(r" {2,}")  # 2 or more spaces

    START_END_TAGS = (  # elements that don't need to be closed in HTML
        "area",
        "base",
        "br",
        "col",
        "command",
        "embed",
        "hr",
        "img",
        "input",
        "keygen",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    )

    def __init__(self) -> None:
        self.root: Node | None = None
        super().__init__()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.START_END_TAGS:
            self.handle_startendtag(tag, attrs)
        else:
            self.root = Node(tag.lower(), dict(attrs), self.root)

    def handle_endtag(self, tag: str) -> None:
        if self.root is not None:
            self.root = self.root.parent or self.root

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        Node(tag.lower(), dict(attrs), self.root)

    def handle_data(self, data: str) -> None:
        if self.root:
            self.root.children.append(data)

    def __str__(self) -> str:
        if self.root is None:  # plain text without any tags
            return ""
        # Remove leading/trailing whitespace of every line.
        lines = str(self.root).strip().split("\n")
        text = "\n".join(line.strip().strip("\ufeff") for line in lines)
        # Sanitize all wide vertical or horizontal spaces.
        return self.DOUBLE_SPACE.sub(" ", self.DOUBLE_NEWLINE.sub("\n\n", text.strip()))


def html_to_text(html: str) -> str:
    """
    Convert a markup fragment into its plain-text alternative.

    Indentation is stripped and runs of blank lines collapse to one. Content that
    no element wraps is dropped, so plain input yields an empty body.
    """
    parser = HTML2TextParser()
    parser.feed(html)
    parser.close()
    return str(parser)
