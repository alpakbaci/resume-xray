"""The shared representation every reader produces and every check consumes (ALGORITHM.md §2.0)."""

from dataclasses import dataclass, field
from typing import Literal

Region = Literal["body", "header", "footer", "table", "textbox"]


@dataclass(frozen=True)
class Word:
    """A PDF word with its box in points, measured from the top-left of the page."""

    text: str
    x0: float
    top: float
    x1: float
    bottom: float
    font_size: float
    bold: bool


@dataclass(frozen=True)
class Line:
    text: str
    page: int
    region: Region = "body"
    font_size: float | None = None
    bold: bool = False
    style: str | None = None
    # (x0, top, x1, bottom) in points; PDF only.
    bbox: tuple[float, float, float, float] | None = None


@dataclass
class Page:
    number: int
    width: float | None
    height: float | None
    # Raw text as a simple ATS would extract it, in the primary reader's order.
    text: str
    # The same page read by a second reader (pypdf); PDF only, None if it failed.
    alt_text: str | None = None
    words: list[Word] = field(default_factory=list)
    lines: list[Line] = field(default_factory=list)
    # Non-whitespace characters found on the page.
    char_count: int = 0
    # Columns declared in the document settings; DOCX only.
    columns: int | None = None


@dataclass
class Document:
    name: str
    kind: Literal["pdf", "docx"]
    pages: list[Page]

    @property
    def lines(self) -> list[Line]:
        return [line for page in self.pages for line in page.lines]
