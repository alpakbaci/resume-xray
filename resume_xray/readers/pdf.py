"""PDF reader: pdfplumber for words, fonts and raw text; pypdf as a second reader (ALGORITHM.md §2.0)."""

import re
from pathlib import Path
from statistics import median

import pdfplumber
from pypdf import PdfReader

from resume_xray.config import load_weights
from resume_xray.models import Document, Line, Page, Word

BOLD_FONT = re.compile(r"bold|black|heavy|semibold|demi", re.IGNORECASE)


def read_pdf(path: Path) -> Document:
    weights = load_weights()
    row_tolerance = weights["reader"]["line_tolerance_pt"]
    split_gap = weights["parseability"]["gutter_min_width_pt"]
    alt_texts = _read_with_pypdf(path)

    pages = []
    with pdfplumber.open(path) as pdf:
        for index, page in enumerate(pdf.pages):
            number = index + 1
            words = [
                Word(
                    text=w["text"],
                    x0=w["x0"],
                    top=w["top"],
                    x1=w["x1"],
                    bottom=w["bottom"],
                    font_size=w["size"],
                    bold=bool(BOLD_FONT.search(w["fontname"])),
                )
                for w in page.extract_words(extra_attrs=["fontname", "size"])
            ]
            pages.append(
                Page(
                    number=number,
                    width=float(page.width),
                    height=float(page.height),
                    text=page.extract_text() or "",
                    alt_text=alt_texts[index] if index < len(alt_texts) else None,
                    words=words,
                    lines=group_lines(words, number, row_tolerance, split_gap),
                    char_count=sum(1 for c in page.chars if not c["text"].isspace()),
                )
            )
    return Document(name=path.name, kind="pdf", pages=pages)


def group_lines(words: list[Word], page: int, row_tolerance: float, split_gap: float) -> list[Line]:
    """Group words into visual rows, then split rows at gaps wide enough to be a column gutter."""
    rows: list[list[Word]] = []
    for word in sorted(words, key=lambda w: (w.top, w.x0)):
        if rows and abs(word.top - rows[-1][0].top) <= row_tolerance:
            rows[-1].append(word)
        else:
            rows.append([word])

    lines = []
    for row in rows:
        row.sort(key=lambda w: w.x0)
        segment = [row[0]]
        for word in row[1:]:
            if word.x0 - segment[-1].x1 > split_gap:
                lines.append(_make_line(segment, page))
                segment = []
            segment.append(word)
        lines.append(_make_line(segment, page))
    return lines


def _make_line(words: list[Word], page: int) -> Line:
    return Line(
        text=" ".join(w.text for w in words),
        page=page,
        font_size=median(w.font_size for w in words),
        bold=sum(w.bold for w in words) * 2 > len(words),
        bbox=(
            min(w.x0 for w in words),
            min(w.top for w in words),
            max(w.x1 for w in words),
            max(w.bottom for w in words),
        ),
    )


def _read_with_pypdf(path: Path) -> list[str | None]:
    """Page texts from pypdf; a page that pypdf cannot read gives None instead of failing."""
    try:
        reader = PdfReader(path)
    except Exception:
        return []
    texts: list[str | None] = []
    for page in reader.pages:
        try:
            texts.append(page.extract_text() or "")
        except Exception:
            texts.append(None)
    return texts
