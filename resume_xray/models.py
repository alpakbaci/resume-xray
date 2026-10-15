"""The shared representation every reader produces and every check consumes (ALGORITHM.md §2.0)."""

from dataclasses import dataclass, field
from typing import Literal

Region = Literal["body", "header", "footer", "table", "textbox"]

# Reading strategies (ALGORITHM.md §1, "How ATSs read a PDF").
PDF_STRATEGIES = ("stream", "position", "columns")
DOCX_STRATEGIES = ("full", "body")
STRATEGY_NAMES = {
    "stream": "content-stream order",
    "position": "position order",
    "columns": "column-aware order",
    "full": "all document parts",
    "body": "body paragraphs only",
}


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
    # Index of the visual row the line belongs to; lines split at a wide gap share a row. PDF only.
    row: int | None = None
    # Font size of each word, in order. PDF only.
    sizes: tuple[float, ...] = ()


@dataclass(frozen=True)
class Gutter:
    """A vertical whitespace channel between two columns, in points."""

    x0: float
    x1: float
    # Vertical stretch where the channel is empty, in points from the top of the page.
    y0: float = 0.0
    y1: float = 0.0

    @property
    def center(self) -> float:
        return (self.x0 + self.x1) / 2


@dataclass
class Page:
    number: int
    width: float | None
    height: float | None
    # The page's text as each reading strategy extracts it; None if that reader failed.
    readings: dict[str, str | None]
    words: list[Word] = field(default_factory=list)
    lines: list[Line] = field(default_factory=list)
    # Non-whitespace characters found on the page.
    char_count: int = 0
    # Share of the page area covered by images, and number of vector curves drawn. PDF only.
    image_coverage: float = 0.0
    curves: int = 0
    # Columns declared in the document settings; DOCX only.
    columns: int | None = None
    gutter: Gutter | None = None
    # Targets of hyperlinks (stored apart from the text, so text extraction does not see them).
    links: list[str] = field(default_factory=list)


@dataclass
class Document:
    name: str
    kind: Literal["pdf", "docx"]
    pages: list[Page]

    @property
    def strategies(self) -> tuple[str, ...]:
        return PDF_STRATEGIES if self.kind == "pdf" else DOCX_STRATEGIES

    def reading(self, strategy: str) -> str | None:
        texts = [page.readings.get(strategy) for page in self.pages]
        if any(t is None for t in texts):
            return None
        return "\n".join(texts)

    @property
    def lines(self) -> list[Line]:
        return [line for page in self.pages for line in page.lines]
