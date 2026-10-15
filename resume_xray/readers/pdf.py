"""PDF reader: pdfplumber for words, fonts and raw text; pypdf as a second reader (ALGORITHM.md §2.0)."""

import re
from io import BytesIO
from statistics import median

import pdfplumber
from pypdf import PdfReader

from resume_xray.config import load_weights
from resume_xray.layout import column_order, find_gutter, reading_order
from resume_xray.models import Document, Line, Page, Word

BOLD_FONT = re.compile(r"bold|black|heavy|semibold|demi", re.IGNORECASE)
BULLETS = "•●▪■◦►"


def read_pdf(source: BytesIO, name: str) -> Document:
    weights = load_weights()
    row_overlap = weights["reader"]["row_overlap_min"]
    split_gap = weights["parseability"]["gutter_min_width_pt"]
    alt_texts = _read_with_pypdf(source)
    source.seek(0)

    pages = []
    with pdfplumber.open(source) as pdf:
        for index, page in enumerate(pdf.pages):
            number = index + 1
            words = words_from_chars(page.chars, weights["reader"]["word_gap_pt"], row_overlap)
            lines = group_lines(words, number, row_overlap, split_gap)
            gutter = find_gutter(lines, float(page.width), weights["parseability"])
            # Keep lines in column-aware reading order, so sections follow their own column.
            lines = [line for row in reading_order(lines, gutter) for line in row]
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
                    image_coverage=min(1.0, sum((i["x1"] - i["x0"]) * (i["bottom"] - i["top"]) for i in page.images) / (float(page.width) * float(page.height))),
                    curves=len(page.curves),
                    gutter=gutter,
                    links=[link["uri"] for link in page.hyperlinks if link.get("uri")],
                )
            )
    return Document(name=name, kind="pdf", pages=pages)


def words_from_chars(chars: list[dict], word_gap: float, row_overlap: float) -> list[Word]:
    """Join characters into words in content-stream order (ALGORITHM.md §2.0).

    A word ends at whitespace, at a horizontal gap wider than word_gap, when the text moves back
    to the left, or when the next character does not overlap the word vertically (row_overlap).
    Font and size never end a word: a letter taken from another font, with another height, stays
    in its word (e.g. the İ of "TÜBİTAK" or a fallback "ı"). A round bullet is always a word of its
    own."""
    words: list[Word] = []
    current: list[dict] = []

    def flush():
        if current:
            words.append(Word(
                text="".join(c["text"] for c in current),
                x0=min(c["x0"] for c in current),
                top=min(c["top"] for c in current),
                x1=max(c["x1"] for c in current),
                bottom=max(c["bottom"] for c in current),
                font_size=median(c["size"] for c in current),
                bold=sum(bool(BOLD_FONT.search(c["fontname"])) for c in current) * 2 > len(current),
            ))
            current.clear()

    for char in chars:
        if char["text"].isspace() or not char.get("upright", True):
            flush()
            continue
        if char["text"] in BULLETS:
            flush()
            current.append(char)
            flush()
            continue
        if current:
            last = current[-1]
            gap = char["x0"] - last["x1"]
            overlap = _overlap_ratio(char["top"], char["bottom"], min(c["top"] for c in current), max(c["bottom"] for c in current))
            if gap > word_gap or char["x0"] < last["x0"] - word_gap or overlap < row_overlap:
                flush()
        current.append(char)
    flush()
    return words


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


def _read_with_pypdf(source: BytesIO) -> list[str | None]:
    """Page texts from pypdf; a page that pypdf cannot read gives None instead of failing."""
    try:
        reader = PdfReader(source)
    except Exception:
        return []
    texts: list[str | None] = []
    for page in reader.pages:
        try:
            texts.append(page.extract_text() or "")
        except Exception:
            texts.append(None)
    return texts
