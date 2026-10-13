"""PDF reader: pdfplumber for words, fonts and raw text; pypdf as a second reader (ALGORITHM.md §2.0)."""

import re
from pathlib import Path
from statistics import median

import pdfplumber
from pypdf import PdfReader

from resume_xray.config import load_weights
from resume_xray.layout import column_order, find_gutter
from resume_xray.models import Document, Line, Page, Word

BOLD_FONT = re.compile(r"bold|black|heavy|semibold|demi", re.IGNORECASE)


def read_pdf(path: Path) -> Document:
    weights = load_weights()
    row_overlap = weights["reader"]["row_overlap_min"]
    split_gap = weights["parseability"]["gutter_min_width_pt"]
    alt_texts = _read_with_pypdf(path)

    pages = []
    with pdfplumber.open(path) as pdf:
        for index, page in enumerate(pdf.pages):
            number = index + 1
            # Font details are taken per character rather than via extra_attrs, which would split a
            # word wherever the font subset changes (e.g. "TÜBİTAK" whose İ comes from another subset).
            words = [
                Word(
                    text=w["text"],
                    x0=w["x0"],
                    top=w["top"],
                    x1=w["x1"],
                    bottom=w["bottom"],
                    font_size=median(c["size"] for c in w["chars"]),
                    bold=sum(bool(BOLD_FONT.search(c["fontname"])) for c in w["chars"]) * 2 > len(w["chars"]),
                )
                for w in page.extract_words(return_chars=True)
            ]
            lines = group_lines(words, number, row_overlap, split_gap)
            gutter = find_gutter(lines, float(page.width), weights["parseability"])
            pages.append(
                Page(
                    number=number,
                    width=float(page.width),
                    height=float(page.height),
                    readings={
                        "stream": alt_texts[index] if index < len(alt_texts) else None,
                        "position": page.extract_text() or "",
                        "columns": column_order(lines, gutter),
                    },
                    words=words,
                    lines=lines,
                    char_count=sum(1 for c in page.chars if not c["text"].isspace()),
                    gutter=gutter,
                    links=[link["uri"] for link in page.hyperlinks if link.get("uri")],
                )
            )
    return Document(name=path.name, kind="pdf", pages=pages)


def group_lines(words: list[Word], page: int, row_overlap: float, split_gap: float) -> list[Line]:
    """Group words into visual rows, then split rows at gaps wide enough to be a column gutter."""
    rows: list[list[Word]] = []
    spans: list[tuple[float, float]] = []
    for word in sorted(words, key=lambda w: (w.top, w.x0)):
        for row, (top, bottom) in zip(rows, spans):
            if _overlap_ratio(word.top, word.bottom, top, bottom) >= row_overlap:
                row.append(word)
                break
        else:
            rows.append([word])
            spans.append((word.top, word.bottom))

    lines = []
    for row_index, row in enumerate(rows):
        # Words starting at the same x: the narrower first. Some PDFs put a tiny invisible bullet
        # glyph exactly over the first letter of the line (the visible bullet is a drawn shape).
        row.sort(key=lambda w: (w.x0, w.x1))
        segment = [row[0]]
        for word in row[1:]:
            if word.x0 - segment[-1].x1 > split_gap:
                lines.append(_make_line(segment, page, row_index))
                segment = []
            segment.append(word)
        lines.append(_make_line(segment, page, row_index))
    return lines


def _overlap_ratio(top_a: float, bottom_a: float, top_b: float, bottom_b: float) -> float:
    shorter = min(bottom_a - top_a, bottom_b - top_b)
    if shorter <= 0:
        return 0.0
    return max(0.0, min(bottom_a, bottom_b) - max(top_a, top_b)) / shorter


def _make_line(words: list[Word], page: int, row: int) -> Line:
    return Line(
        text=" ".join(w.text for w in words),
        page=page,
        row=row,
        sizes=tuple(w.font_size for w in words),
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
