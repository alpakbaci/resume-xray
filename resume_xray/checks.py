"""Parseability checks (ALGORITHM.md §2). Each check returns findings; nothing here is scored."""

import re
import tomllib
from functools import cache
from importlib.resources import files
from statistics import median

from rapidfuzz import fuzz
from rapidfuzz.distance import Indel

from resume_xray.config import load_weights
from resume_xray.layout import side
from resume_xray.models import STRATEGY_NAMES, Document, Line
from resume_xray.report import Finding, Report
from resume_xray.text import BULLETS, fold, original_words, tokens

CORE_SECTIONS = ("experience", "education", "skills")
# Bullets whose position can be checked; dashes also appear inside lines ("2021 – 2023").
ROUND_BULLETS = "•●▪■◦►"

CID = re.compile(r"\(cid:\d+\)")
PRIVATE_USE = re.compile("[-�]")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE = re.compile(r"\+?\d[\d\s().-]{8,}\d")
LINKEDIN = re.compile(r"linkedin\.com/in/[\w%-]+", re.IGNORECASE)
YEAR = r"(?:19|20)\d{2}"
VAGUE_DATE = re.compile(
    rf"\b(?:summer|winter|spring|fall|autumn|yaz|kış|kis|bahar|ilkbahar|sonbahar|güz|guz|q[1-4])\s+{YEAR}\b",
    re.IGNORECASE,
)


def run_checks(document: Document) -> Report:
    weights = load_weights()["parseability"]
    findings: list[Finding] = []
    findings += check_text_layer(document, weights)
    findings += check_garbled(document, weights)
    findings += check_reading_order(document, weights)
    findings += check_outside_body(document, weights)
    sections, section_findings = check_sections(document, weights)
    findings += section_findings
    fields, field_findings = check_fields(document, weights)
    findings += field_findings
    findings += check_bullets(document, weights)
    order = {"critical": 0, "warning": 1, "info": 2}
    findings.sort(key=lambda f: (order[f.severity], f.check))
    return Report(
        document=document.name,
        kind=document.kind,
        pages=len(document.pages),
        findings=findings,
        sections={name: line.text for name, line in sections.items()},
        fields=fields,
        section_lines=sections,
    )


def names(strategies) -> str:
    return ", ".join(STRATEGY_NAMES[s] for s in strategies)


def structured_text(document: Document) -> str:
    """The best reading we have: column-aware order for PDF, every part for DOCX."""
    return document.reading("columns" if document.kind == "pdf" else "full") or ""


# 2.1 ---------------------------------------------------------------------------------------------


def check_text_layer(document: Document, weights: dict) -> list[Finding]:
    minimum = weights["min_chars_per_page"]
    if document.kind == "pdf":
        # A short last page is not a scan: the page must also hold an image or outlined text.
        empty = [
            p.number
            for p in document.pages
            if p.char_count < minimum
            and (p.image_coverage >= weights["scan_image_coverage"] or p.curves >= weights["outline_min_curves"])
        ]
    else:
        empty = [p.number for p in document.pages if p.char_count < minimum]
    if not empty:
        return []
    where = f"Page {', '.join(map(str, empty))} has" if document.kind == "pdf" else "The document has"
    return [
        Finding(
            check="2.1",
            severity="critical",
            title="No text layer",
            code="no_text_layer",
            params={"pages": empty},
            detail=f"{where} fewer than {minimum} characters of text. It is most likely a scanned image "
            "or text converted to outlines, so an ATS without OCR sees nothing there.",
            fix="Export the resume from the original editor (Word, Google Docs, ...) as a text PDF.",
            strategies=document.strategies,
            pages=tuple(empty) if document.kind == "pdf" else (),
        )
    ]


# 2.2 ---------------------------------------------------------------------------------------------


def check_garbled(document: Document, weights: dict) -> list[Finding]:
    text = structured_text(document)
    cids = CID.findall(text)
    others = PRIVATE_USE.findall(text)
    total = sum(1 for c in CID.sub("x", text) if not c.isspace())
    if not total:
        return []
    ratio = (len(cids) + len(others)) / total
    if ratio <= weights["garbled_warn"]:
        return []
    examples = sorted({w for w in text.split() if CID.search(w) or PRIVATE_USE.search(w)})[:6]
    return [
        Finding(
            check="2.2",
            severity="critical" if ratio > weights["garbled_critical"] else "warning",
            title="Unreadable characters",
            code="garbled",
            params={"ratio": round(ratio, 3)},
            detail=f"{ratio:.0%} of the characters cannot be turned into text (fonts without a "
            "character map, or icon fonts). An ATS stores them as garbage.",
            fix="Use a standard font and replace icons with plain words (Email:, Phone:).",
            strategies=document.strategies,
            examples=tuple(examples),
        )
    ]


# 2.3 and 2.4 -------------------------------------------------------------------------------------


def check_reading_order(document: Document, weights: dict) -> list[Finding]:
    if document.kind != "pdf":
        return []
    findings = []
    column_pages: dict[str, list[int]] = {}
    plain_pages: dict[str, list[int]] = {}
    failed: set[str] = set()
    for page in document.pages:
        reference = tokens(page.readings["columns"])
        if not reference:
            continue
        for strategy in ("stream", "position"):
            text = page.readings[strategy]
            if text is None:
                failed.add(strategy)
                continue
            scrambled = Indel.normalized_similarity(tokens(text), reference) < weights["agreement_order_max"]
            if page.gutter and not scrambled:
                scrambled = mixes_columns(page, text)
            if scrambled:
                target = column_pages if page.gutter else plain_pages
                target.setdefault(strategy, []).append(page.number)

    gutter_pages = [p.number for p in document.pages if p.gutter]
    if gutter_pages:
        affected = tuple(s for s in ("stream", "position") if s in column_pages)
        findings.append(
            Finding(
                check="2.3",
                severity="warning" if affected else "info",
                title="Multi-column layout" + (" scrambles the reading order" if affected else ""),
                code="columns_scramble" if affected else "columns_ok",
                detail=(
                    f"Readers using {names(affected)} mix the columns, so text from one section "
                    "ends up inside another."
                    if affected
                    else "Columns were detected, but every reading strategy keeps them apart."
                ),
                fix="Use a single-column layout, or check the raw text with --raw." if affected else None,
                strategies=affected,
                pages=tuple(gutter_pages),
            )
        )
    if plain_pages:
        affected = tuple(s for s in ("stream", "position") if s in plain_pages)
        findings.append(
            Finding(
                check="2.4",
                severity="warning",
                title="Reading order differs between readers",
                code="order_differs",
                detail=f"Readers using {names(affected)} put the text in a different order than it "
                "appears on the page.",
                fix="Check the raw text with --raw; layouts built from floating text boxes often cause this.",
                strategies=affected,
                pages=tuple(sorted({n for pages in plain_pages.values() for n in pages})),
            )
        )
    if failed:
        findings.append(
            Finding(
                check="2.4",
                severity="warning",
                title="A reader could not open the file",
                code="reader_failed",
                detail=f"Readers using {names(sorted(failed))} failed on this PDF.",
                fix="Re-export the PDF from the original editor.",
                strategies=tuple(sorted(failed)),
            )
        )

    structured = structured_text(document)
    as_written = original_words(structured)
    reference_words = set(tokens(structured))
    for strategy in ("stream", "position"):
        text = document.reading(strategy)
        if text is None:
            continue
        lost = reference_words - set(tokens(text))
        if lost:
            findings.append(
                Finding(
                    check="2.4",
                    severity="warning",
                    title="Words broken or lost",
                    code="words_broken",
                    detail=f"Readers using {names([strategy])} do not see these words as written, "
                    "usually because a letter is split off (for example a Turkish İ drawn from a "
                    "separate font). A recruiter searching for them will not find this resume.",
                    fix="Re-export with a font that includes all letters of your language.",
                    strategies=(strategy,),
                    examples=tuple(sorted(as_written.get(w, w) for w in lost)[:8]),
                )
            )
    return findings


def mixes_columns(page, text: str) -> bool:
    """True when a reading joins text from both sides of the gutter, side by side, on one line."""
    rows: dict[int, tuple[list[str], list[str]]] = {}
    for line in page.lines:
        where = side(line, page.gutter)
        if where:
            rows.setdefault(line.row, ([], []))[where == "right"].append(fold(line.text))
    output = [f" {fold(line)} " for line in text.splitlines()]
    return any(
        f" {a} {b} " in out
        for left, right in rows.values()
        for l in left if l
        for r in right if r
        for a, b in ((l, r), (r, l))
        for out in output
    )


# 2.5 ---------------------------------------------------------------------------------------------


def check_outside_body(document: Document, weights: dict) -> list[Finding]:
    if document.kind != "docx":
        return []
    findings = []
    lines = document.lines
    header_footer = [l.text for l in lines if l.region in ("header", "footer")]
    contact = [t for t in header_footer if has_contact(t, weights)]
    if contact and not has_contact(document.reading("body") or "", weights):
        findings.append(
            Finding(
                check="2.5",
                severity="warning",
                title="Contact details only in the header or footer",
                code="contact_in_header",
                detail="Word stores headers and footers apart from the body. Readers that take only "
                "the body paragraphs never see your email or phone number.",
                fix="Move your contact details into the first lines of the body.",
                strategies=("body",),
                examples=tuple(contact[:3]),
            )
        )
    boxes = [l.text for l in lines if l.region == "textbox"]
    if boxes:
        findings.append(
            Finding(
                check="2.5",
                severity="warning",
                title="Text inside text boxes",
                code="text_boxes",
                detail="Text boxes are stored inside drawings. Readers that take only the body "
                "paragraphs skip them.",
                fix="Replace text boxes with normal paragraphs.",
                strategies=("body",),
                examples=tuple(boxes[:3]),
            )
        )
    return findings


# 2.6 ---------------------------------------------------------------------------------------------


@cache
def heading_dictionary() -> dict[str, tuple[str, ...]]:
    raw = tomllib.loads(files("resume_xray.data").joinpath("headings.toml").read_text(encoding="utf-8"))
    return {name: tuple(fold(v) for v in variants) for name, variants in raw.items()}


def match_heading(text: str, minimum: float) -> tuple[str | None, str, float]:
    """(section name or None, closest section name, best score)."""
    key = fold(text)
    best_name, best_score = "", 0.0
    for name, variants in heading_dictionary().items():
        score = max(fuzz.ratio(key, v) for v in variants)
        if score > best_score:
            best_name, best_score = name, score
    return (best_name if best_score >= minimum else None), best_name, best_score


def heading_candidates(document: Document, weights: dict) -> list[Line]:
    sizes = [s for line in document.lines for s in (line.sizes or ([line.font_size] if line.font_size else []))]
    body_size = median(sizes) if sizes else None
    candidates = []
    for line in document.lines:
        words = line.text.split()
        if not words or len(words) > weights["heading_max_words"] or line.text[0] in BULLETS:
            continue
        letters = [c for c in line.text if c.isalpha()]
        styled = (
            line.bold
            or (letters and all(c.isupper() for c in letters))
            or (body_size and line.font_size and line.font_size >= weights["heading_size_ratio"] * body_size)
            or (line.style or "").startswith(("Heading", "Title"))
        )
        if styled:
            candidates.append(line)
    return candidates


def _style(line: Line) -> tuple:
    letters = [c for c in line.text if c.isalpha()]
    return (round(line.font_size or 0, 1), line.bold, bool(letters) and all(c.isupper() for c in letters))


def check_sections(document: Document, weights: dict) -> tuple[dict[str, Line], list[Finding]]:
    minimum = weights["heading_match_min"]
    sections: dict[str, Line] = {}
    unmatched: list[tuple[Line, str]] = []
    for line in heading_candidates(document, weights):
        name, closest, _ = match_heading(line.text, minimum)
        if name:
            sections.setdefault(name, line)
        else:
            unmatched.append((line, closest))

    findings = []
    heading_styles = {_style(line) for line in sections.values()}
    first = min((document.lines.index(l) for l in sections.values()), default=None)
    unknown = [
        (line, closest)
        for line, closest in unmatched
        if _style(line) in heading_styles and first is not None and document.lines.index(line) > first
    ]
    if unknown:
        findings.append(
            Finding(
                check="2.6",
                severity="warning",
                title="Section heading not recognized",
                code="heading_unknown",
                params={"suggestions": {line.text: heading_label(closest) for line, closest in unknown[:5]}},
                detail="These lines look like section headings but are not standard names, so a "
                "parser may not know which field to fill with what follows.",
                fix="Use standard headings: " + ", ".join(
                    f'"{line.text}" → "{heading_label(closest)}"' for line, closest in unknown[:5]
                ),
                examples=tuple(line.text for line, _ in unknown[:5]),
            )
        )

    missing = [name for name in CORE_SECTIONS if name not in sections]
    if missing:
        findings.append(
            Finding(
                check="2.6",
                severity="warning",
                title="Standard section not found",
                code="section_missing",
                detail="No heading was recognized for: " + ", ".join(heading_label(n) for n in missing)
                + ". Parsers fill these fields from the text under such headings.",
                fix="Add the section with a standard heading.",
                examples=tuple(heading_label(n) for n in missing),
            )
        )

    merged: dict[str, list[str]] = {}
    for strategy in document.strategies:
        text = document.reading(strategy)
        if text is None:
            continue
        own_lines = {fold(t) for t in text.splitlines()}
        for line in sections.values():
            if line.region in ("body", "table") or strategy == "full":
                if fold(line.text) not in own_lines:
                    merged.setdefault(strategy, []).append(line.text)
    if merged:
        headings = sorted({h for hs in merged.values() for h in hs})
        findings.append(
            Finding(
                check="2.6",
                severity="warning",
                title="Section headings run into other text",
                code="heading_merged",
                detail=f"Readers using {names(merged)} put these headings on a line together with "
                "other text, so they may not be recognized as headings.",
                fix="Give each heading its own full-width line.",
                strategies=tuple(s for s in document.strategies if s in merged),
                examples=tuple(headings[:6]),
            )
        )
    return sections, findings


def heading_label(name: str) -> str:
    raw = tomllib.loads(files("resume_xray.data").joinpath("headings.toml").read_text(encoding="utf-8"))
    return raw[name][0]


# 2.7 ---------------------------------------------------------------------------------------------


def check_fields(document: Document, weights: dict) -> tuple[dict[str, str], list[Finding]]:
    findings = []
    fields: dict[str, str] = {}
    readings = {s: document.reading(s) for s in document.strategies}
    readings = {s: t for s, t in readings.items() if t is not None}
    structured = structured_text(document)

    email = EMAIL.search(structured)
    if email:
        fields["email"] = email.group()
    phone = find_phone(structured, weights)
    if phone:
        fields["phone"] = phone
    linkedin = LINKEDIN.search(structured)
    if linkedin:
        fields["linkedin"] = linkedin.group()

    if not any(EMAIL.search(t) for t in readings.values()):
        findings.append(
            Finding(
                check="2.7",
                severity="critical",
                title="No email address found",
                code="no_email",
                detail="No reader finds an email address, so an ATS cannot fill in how to contact you.",
                fix="Write your email address as plain text near the top.",
                strategies=tuple(readings),
            )
        )
    hidden = [link for link in _links(document) if LINKEDIN.search(link)]
    if hidden and not linkedin:
        findings.append(
            Finding(
                check="2.7",
                severity="info",
                title="LinkedIn address is only a hidden link",
                code="linkedin_hidden",
                detail="Your LinkedIn URL is attached to other text as a link. Text extraction reads "
                "the visible text, not the link target, so the URL itself is not in the parsed resume.",
                fix="Write the address as text, e.g. linkedin.com/in/your-name.",
                examples=(hidden[0],),
            )
        )

    vague = sorted({m.group() for m in VAGUE_DATE.finditer(structured)})
    if vague:
        findings.append(
            Finding(
                check="2.7",
                severity="warning",
                title="Dates that cannot be parsed",
                code="vague_dates",
                detail="Dates written with a season or quarter cannot be turned into a month, so the "
                "ATS cannot compute how long you held a position.",
                fix='Use "MM/YYYY" or "Mon YYYY", e.g. "06/2021 – 09/2021".',
                examples=tuple(vague[:5]),
            )
        )
    return fields, findings


def find_phone(text: str, weights: dict) -> str | None:
    low, high = weights["phone_min_digits"], weights["phone_max_digits"]
    return next((m.group().strip() for m in PHONE.finditer(text) if low <= sum(c.isdigit() for c in m.group()) <= high), None)


def has_contact(text: str, weights: dict) -> bool:
    return bool(EMAIL.search(text) or find_phone(text, weights))


def _links(document: Document) -> list[str]:
    return [link for page in document.pages for link in page.links]


# 2.8 ---------------------------------------------------------------------------------------------


def check_bullets(document: Document, weights: dict) -> list[Finding]:
    if document.kind != "pdf":
        return []
    bullet_lines = [l for l in document.lines if l.text[:1] in ROUND_BULLETS]
    if not bullet_lines:
        return []
    tiny = [
        l
        for l in bullet_lines
        if len(l.sizes) > 1 and l.sizes[0] < weights["bullet_size_ratio"] * median(l.sizes[1:])
    ]
    affected = []
    for strategy in ("stream", "position"):
        text = document.reading(strategy)
        if text is None:
            continue
        misplaced = sum(
            1
            for line in text.splitlines()
            for i, c in enumerate(line.strip())
            if c in ROUND_BULLETS and (i > 0 or len(line.strip()) == 1)
        )
        if misplaced:
            affected.append((strategy, misplaced))
    if not affected:
        return []
    cause = (
        " The bullets are tiny glyphs drawn apart from the text (the visible bullet is a shape), "
        "which is typical of HTML-to-PDF exports."
        if tiny
        else ""
    )
    return [
        Finding(
            check="2.8",
            severity="warning",
            title="Bullets end up in the wrong place",
            code="bullets_misplaced",
            params={"counts": dict(affected), "total": len(bullet_lines), "tiny": bool(tiny)},
            detail="; ".join(f"{names([s])}: {n} of {len(bullet_lines)} bullets misplaced" for s, n in affected)
            + ". Items then appear to start in the middle of the previous one." + cause,
            fix="Use the editor's normal bullet list, or export the PDF with another tool.",
            strategies=tuple(s for s, _ in affected),
        )
    ]
