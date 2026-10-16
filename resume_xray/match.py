"""Job match (ALGORITHM.md §3): weighted coverage of the job's terms, plus separate checks."""

import math
import re
import tomllib
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from functools import cache
from importlib.resources import files
from typing import Literal

import snowballstemmer
from rapidfuzz import fuzz

from resume_xray.config import load_weights
from resume_xray.models import Document, Line
from resume_xray.text import fold

Level = Literal["exact", "word_form", "synonym", "missing"]

TOKEN = re.compile(r"\.?\w[\w+#.&]*")
APOSTROPHE_SUFFIX = re.compile(r"(?<=\w)['’]\w+")
TECHNICAL = re.compile(r"(?=.*[a-zA-Z])(?:.*[\d+#]|.*[a-z][A-Z])|[A-Z]{2,}$")
_ASCII = str.maketrans({"ı": "i", "ğ": "g", "ş": "s", "ç": "c", "ö": "o", "ü": "u", "â": "a", "î": "i", "û": "u"})
STOPWORDS = {
    "en": {"the", "and", "with", "for", "of", "to", "in", "a", "an", "is", "are", "you", "we", "our", "will", "be", "on", "as", "or", "your"},
    "tr": {"ve", "ile", "bir", "bu", "için", "olan", "da", "de", "en", "az", "olarak", "veya", "gibi", "çok", "her", "ilgili", "konusunda", "sahip", "deneyimli", "tercihen"},
}


# Normalization (§3.1) ----------------------------------------------------------------------------


@dataclass(frozen=True)
class Token:
    original: str
    surface: str
    stem: str
    # Character offsets in the analyzed text.
    start: int = 0
    end: int = 0


def detect_language(text: str) -> str:
    words = re.findall(r"\w+", lower(text, "tr"))
    return "tr" if sum(w in STOPWORDS["tr"] for w in words) > sum(w in STOPWORDS["en"] for w in words) else "en"


def lower(text: str, language: str) -> str:
    """Turkish-aware lowercasing: in Turkish text I is ı; İ is i in every language."""
    if language == "tr":
        text = text.replace("I", "ı")
    return text.replace("İ", "i").lower()


def ascii_key(word: str) -> str:
    word = unicodedata.normalize("NFKD", word.translate(_ASCII))
    return "".join(c for c in word if not unicodedata.combining(c))


@cache
def _stemmer(language: str):
    return snowballstemmer.stemmer("turkish" if language == "tr" else "english")


def analyze(text: str, language: str) -> list[Token]:
    """Tokens with an exact key (surface) and a stemmed key. Suffixes after an apostrophe
    ("Python'da") are dropped; +, #, . and & stay inside terms (C++, C#, .NET, R&D)."""
    tokens = []
    # Blank the suffix out instead of removing it, so offsets still point into the original text.
    for match in TOKEN.finditer(APOSTROPHE_SUFFIX.sub(lambda m: " " * len(m.group()), text)):
        original = match.group().rstrip(".&")
        if not original:
            continue
        lowered = lower(original, language)
        surface = ascii_key(lowered)
        stem = ascii_key(_stemmer(language).stemWord(lowered)) if lowered.isalpha() else surface
        tokens.append(Token(original, surface, stem, match.start(), match.start() + len(original)))
    return tokens


def span_text(text: str, tokens: list[Token]) -> str:
    return text[tokens[0].start : tokens[-1].end]


def find(tokens: list[Token], pattern: list[Token], by: str) -> list[int]:
    """Start positions where `pattern` occurs in `tokens`, comparing surface or stem keys.
    A one-token pattern of at most two characters, or a wording marked case-sensitive in the
    dictionary, must also match its capitals; a one-token pattern compared by stem must be close
    in length (word_form_max_extra)."""
    n = len(pattern)
    if not n:
        return []
    strict = (n == 1 and len(pattern[0].original) <= 2) or case_sensitive(" ".join(t.original for t in pattern))
    max_extra = load_weights()["match"]["word_form_max_extra"]
    hits = []
    for i in range(len(tokens) - n + 1):
        window = tokens[i : i + n]
        if not all(getattr(a, by) == getattr(b, by) for a, b in zip(window, pattern)):
            continue
        if strict and [t.original for t in window] != [t.original for t in pattern]:
            continue
        if by == "stem" and n == 1 and abs(len(window[0].surface) - len(pattern[0].surface)) > max_extra:
            continue
        hits.append(i)
    return hits


# Dictionaries ------------------------------------------------------------------------------------


@cache
def _data(name: str) -> dict:
    return tomllib.loads(files("resume_xray.data").joinpath(name).read_text(encoding="utf-8"))


CASE_MARK = "="


@cache
def _skills() -> tuple[dict[str, list[str]], frozenset[str], frozenset[str]]:
    """Wordings without their case mark, the wordings that must match their capitals, and the keys
    of general and soft skills (soft_skills.toml), which are shown but not counted."""
    entries, exact, general = {}, set(), set()
    for name in ("skills.toml", "soft_skills.toml"):
        for key, wordings in _data(name).items():
            entries[key] = [w.removeprefix(CASE_MARK) for w in wordings]
            exact |= {w.removeprefix(CASE_MARK) for w in wordings if w.startswith(CASE_MARK)}
            if name == "soft_skills.toml":
                general.add(key)
    return entries, frozenset(exact), frozenset(general)


def skills() -> dict[str, list[str]]:
    return _skills()[0]


def is_general(key: str) -> bool:
    """A general or soft skill (communication, proactiveness): shown, not counted (§3.2)."""
    return key in _skills()[2]


def case_sensitive(wording: str) -> bool:
    """A dictionary wording marked with "=" ("=GEO") matches only with the same capitals."""
    return wording in _skills()[1]


# Terms of the job description (§3.2, §3.3) -------------------------------------------------------


@dataclass
class JobTerm:
    key: str
    name: str
    requirement: float
    count: int = 0
    # The wordings the job description used, as written.
    wordings: list[str] = field(default_factory=list)
    # "job" when extracted from the job description, "user" when the user added it.
    source: Literal["job", "user"] = "job"

    @property
    def weight(self) -> float:
        return self.requirement * (1 + math.log(1 + self.count))


@dataclass
class JobDescription:
    language: str
    title: str | None
    terms: list[JobTerm]
    lines: list[tuple[str, float]]  # (line, requirement factor) for lines that count


def section_kind(line: str, weights: dict) -> str | None:
    text = line.strip().rstrip(":").strip()
    if not text or len(text.split()) > weights["heading_max_words"]:
        return None
    key = fold(text)
    best_kind, best = None, 0.0
    for kind in ("required", "preferred", "ignored"):
        for heading in _data("job_sections.toml")[kind]:
            score = fuzz.ratio(key, fold(heading))
            if score > best:
                best_kind, best = kind, score
    return best_kind if best >= weights["heading_match_min"] else None


def parse_job(text: str, title: str | None = None, add: list[str] = (), remove: list[str] = ()) -> JobDescription:
    weights = load_weights()
    pw, mw = weights["parseability"], weights["match"]
    language = detect_language(text)
    cues = [fold(c) for c in _data("job_sections.toml")["preferred_cues"]]
    section = "required"
    seen_heading = False
    counted: list[tuple[str, float]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        kind = section_kind(line, pw)
        if kind:
            section, seen_heading = kind, True
            continue
        if title is None and not counted and not seen_heading and len(line.split()) <= mw["title_max_words"]:
            title = line
        if section == "ignored":
            continue
        folded = f" {fold(line)} "
        preferred = section == "preferred" or any(f" {c} " in folded for c in cues)
        counted.append((line, mw["preferred_weight"] if preferred else mw["required_weight"]))

    variants = sorted(
        ((key, variant, analyze(variant, language)) for key, vs in skills().items() for variant in vs),
        key=lambda item: -len(item[2]),
    )
    terms: dict[str, JobTerm] = {}
    for line, requirement in counted:
        tokens = analyze(line, language)
        used: set[int] = set()
        for key, variant, pattern in variants:
            for start in find(tokens, pattern, "stem"):
                span = set(range(start, start + len(pattern)))
                if span & used:
                    continue
                used |= span
                wording = span_text(line, tokens[start : start + len(pattern)])
                _add(terms, key, skills()[key][0], requirement, wording)
        for i, token in enumerate(tokens):
            if i not in used and TECHNICAL.match(token.original) and token.surface not in STOPWORDS[language]:
                _add(terms, f"word:{token.surface}", token.original, requirement, token.original)

    # Terms the user added (§3.2, user terms): always required.
    for name in (n.strip() for n in add):
        if not name:
            continue
        key = dictionary_key(name) or f"user:{fold(name)}"
        pattern = analyze(name, language)
        count = sum(len(find(analyze(line, language), pattern, "stem")) for line, _ in counted)
        term = terms.get(key)
        if term is None:
            term = terms[key] = JobTerm(key, skills()[key][0] if key in skills() else name, 0, max(count, 1))
        term.requirement = mw["required_weight"]
        term.source = "user"
        if name not in term.wordings:
            term.wordings.append(name)

    removed = {fold(n) for n in remove if n.strip()}
    kept = [t for t in terms.values() if not ({fold(t.name), *map(fold, t.wordings)} & removed)]
    return JobDescription(language, title, kept, counted)


def dictionary_key(name: str) -> str | None:
    """The skill whose wordings include `name`, compared after folding."""
    key = fold(name)
    return next((k for k, variants in skills().items() if any(fold(v) == key for v in variants)), None)


def _add(terms: dict[str, JobTerm], key: str, name: str, requirement: float, wording: str) -> None:
    term = terms.setdefault(key, JobTerm(key, name, requirement))
    term.requirement = max(term.requirement, requirement)
    term.count += 1
    if wording not in term.wordings:
        term.wordings.append(wording)


# Matching the resume (§3.4, §3.5) ----------------------------------------------------------------


@dataclass
class TermResult:
    name: str
    kind: Literal["required", "preferred"]
    weight: float
    level: Level
    job_wording: str
    resume_wording: str | None = None
    # Resume sections where the term appears.
    sections: tuple[str, ...] = ()
    # Reading strategies in which the term is not found although it is in the resume.
    lost_in: tuple[str, ...] = ()
    source: Literal["job", "user"] = "job"
    # A general or soft skill taken from the job ad: shown, not counted in the coverage.
    general: bool = False


@dataclass
class MatchReport:
    job_title: str | None
    required_coverage: float | None
    preferred_coverage: float | None
    terms: list[TermResult]
    title_match: str | None = None
    years_required: int | None = None
    years_in_resume: float | None = None
    degree_required: str | None = None
    degree_in_resume: str | None = None


def match_job(
    document: Document,
    job_text: str,
    sections: dict[str, Line],
    title: str | None = None,
    add: list[str] = (),
    remove: list[str] = (),
) -> MatchReport:
    weights = load_weights()
    mw = weights["match"]
    job = parse_job(job_text, title, add, remove)
    reference = document.reading("columns" if document.kind == "pdf" else "full") or ""
    language = detect_language(reference)
    resume = analyze(reference, language)
    line_sections = _line_sections(document, sections)
    headings = {name: line.text for name, line in sections.items()}
    readings = {s: analyze(t, language) for s in document.strategies if (t := document.reading(s)) is not None}

    results = []
    for term in job.terms:
        level, found = _match_term(term, resume, language)
        result = TermResult(
            name=term.name,
            kind="required" if term.requirement >= mw["required_weight"] else "preferred",
            weight=term.weight,
            level=level,
            job_wording=term.wordings[0],
            source=term.source,
            general=term.source == "job" and is_general(term.key),
        )
        if found:
            result.resume_wording = span_text(reference, found)
            result.sections = tuple(
                dict.fromkeys(
                    headings.get(section, "Top of the resume")
                    for line, section in line_sections
                    if find(analyze(line.text, language), found, "surface")
                )
            )
            result.lost_in = tuple(s for s, tokens in readings.items() if not find(tokens, found, "surface"))
        results.append(result)

    levels = {"exact": 1.0, "word_form": mw["word_form_match"], "synonym": mw["synonym_match"], "missing": 0.0}
    report = MatchReport(
        job_title=job.title,
        required_coverage=_coverage([r for r in results if r.kind == "required" and not r.general], levels),
        preferred_coverage=_coverage([r for r in results if r.kind == "preferred" and not r.general], levels),
        terms=sorted(results, key=lambda r: (r.kind != "required", -r.weight, r.name.lower())),
    )
    report.title_match = _title_match(job.title, document, language)
    report.years_required = _years_required(job)
    report.years_in_resume = _years_in_resume(line_sections)
    report.degree_required = _degree(" ".join(line for line, _ in job.lines), lowest=True)
    education = " ".join(l.text for l, s in line_sections if s == "education") or reference
    report.degree_in_resume = _degree(education, lowest=False)
    return report


def _match_term(term: JobTerm, resume: list[Token], language: str) -> tuple[Level, list[Token] | None]:
    job_patterns = [analyze(w, language) for w in term.wordings]
    for by, level in (("surface", "exact"), ("stem", "word_form")):
        for pattern in job_patterns:
            hits = find(resume, pattern, by)
            if hits:
                return level, resume[hits[0] : hits[0] + len(pattern)]
    if term.key in skills():
        for variant in skills()[term.key]:
            pattern = analyze(variant, language)
            for by in ("surface", "stem"):
                hits = find(resume, pattern, by)
                if hits:
                    return "synonym", resume[hits[0] : hits[0] + len(pattern)]
    return "missing", None


def _coverage(results: list[TermResult], levels: dict[str, float]) -> float | None:
    total = sum(r.weight for r in results)
    if not total:
        return None
    return sum(r.weight * levels[r.level] for r in results) / total


def _line_sections(document: Document, sections: dict[str, Line]) -> list[tuple[Line, str | None]]:
    """Each line with the canonical name of the resume section it belongs to (None before the first)."""
    headings = {id(line): name for name, line in sections.items()}
    current = None
    out = []
    for line in document.lines:
        current = headings.get(id(line), current)
        out.append((line, current))
    return out


# Separate checks (§3.6) --------------------------------------------------------------------------


def _title_match(title: str | None, document: Document, language: str) -> str | None:
    """The first resume line containing the job title as an exact phrase, like a quoted search."""
    if not title:
        return None
    pattern = analyze(title, language)
    return next((line.text for line in document.lines if find(analyze(line.text, language), pattern, "surface")), None)


YEARS_REQUIRED = re.compile(r"(\d{1,2})\s*\+?\s*(?:years?|yrs?|yil|sene)\b")


def _years_required(job: JobDescription) -> int | None:
    found = [int(m.group(1)) for line, _ in job.lines for m in YEARS_REQUIRED.finditer(ascii_key(lower(line, job.language)))]
    return max(found) if found else None


MONTHS = {
    "jan": 1, "january": 1, "oca": 1, "ocak": 1, "feb": 2, "february": 2, "sub": 2, "subat": 2,
    "mar": 3, "march": 3, "mart": 3, "apr": 4, "april": 4, "nis": 4, "nisan": 4, "may": 5, "mayis": 5,
    "jun": 6, "june": 6, "haz": 6, "haziran": 6, "jul": 7, "july": 7, "tem": 7, "temmuz": 7,
    "aug": 8, "august": 8, "agu": 8, "agustos": 8, "sep": 9, "sept": 9, "september": 9, "eyl": 9, "eylul": 9,
    "oct": 10, "october": 10, "eki": 10, "ekim": 10, "nov": 11, "november": 11, "kas": 11, "kasim": 11,
    "dec": 12, "december": 12, "ara": 12, "aralik": 12,
}
PRESENT = r"present|current|now|today|ongoing|gunumuz|halen|hala|devam ediyor|su an"
DATE_ITEM = re.compile(rf"(?:(\d{{1,2}})[/.](\d{{4}})|([a-z]{{3,9}})\.?\s+(\d{{4}})|\b(\d{{4}})\b|\b({PRESENT})\b)")
RANGE_JOINER = re.compile(r"^\s*(?:[-–—]|to|until|\s)\s*$")
DANGLING_JOINER = re.compile(r"\s*(?:[-–—]|to|until)\s*")


def _date_items(text: str) -> list[tuple[int, int, tuple[int, int] | None]]:
    """(start, end, (year, month) or None for 'present') for every date in the text."""
    items = []
    for m in DATE_ITEM.finditer(text):
        month_num, year_num, month_name, named_year, year_only, present = m.groups()
        if present:
            today = date.today()
            items.append((m.start(), m.end(), (today.year, today.month)))
        elif month_num and 1 <= int(month_num) <= 12:
            items.append((m.start(), m.end(), (int(year_num), int(month_num))))
        elif month_name in MONTHS:
            items.append((m.start(), m.end(), (int(named_year), MONTHS[month_name])))
        elif year_only or named_year:
            items.append((m.start(), m.end(), (int(year_only or named_year), 0)))
    return items


def _years_in_resume(line_sections: list[tuple[Line, str | None]]) -> float | None:
    """Total time covered by the date ranges in the experience section, overlaps counted once.
    A year without a month starts in January and ends in December."""
    intervals = []
    lines = [ascii_key(lower(line.text, "tr")) for line, section in line_sections if section == "experience"]
    for i, text in enumerate(lines):
        items = _date_items(text)
        pairs = [(a, b) for (_, end_a, a), (start_b, _, b) in zip(items, items[1:]) if RANGE_JOINER.match(text[end_a:start_b])]
        # In a narrow column a range can wrap, with the employer in between:
        # "Jan 2021 –" / "Northwind Apps" / "Present". The end is the next line that starts with a date.
        if items and DANGLING_JOINER.fullmatch(text[items[-1][1]:]):
            for following in lines[i + 1 : i + 3]:
                nxt = _date_items(following)
                if nxt and nxt[0][0] == 0:
                    pairs.append((items[-1][2], nxt[0][2]))
                    break
        for a, b in pairs:
            start = a[0] * 12 + max(a[1], 1) - 1
            stop = b[0] * 12 + (b[1] or 12) - 1
            if start <= stop:
                intervals.append((start, stop))
    if not intervals:
        return None
    total, current = 0, None
    for start, stop in sorted(intervals):
        if current and start <= current[1] + 1:
            current = (current[0], max(current[1], stop))
        else:
            if current:
                total += current[1] - current[0] + 1
            current = (start, stop)
    total += current[1] - current[0] + 1
    return round(total / 12, 1)


DEGREES = (
    ("PhD", r"phd|ph d|doctorate|doctoral|doktora"),
    ("Master", r"masters?|msc|m sc|mba|yuksek lisans"),
    ("Bachelor", r"bachelors?|bsc|b sc|undergraduate|lisans|universite mezunu"),
)


def _degree(text: str, lowest: bool) -> str | None:
    """The lowest (job: minimum asked) or highest (resume) degree level mentioned."""
    key = f" {fold(text)} "
    found = []
    for name, pattern in DEGREES:
        regex = re.compile(rf"(?<= )(?:{pattern})(?= )")
        if regex.search(key):
            found.append(name)
            key = regex.sub(" ", key)
    if not found:
        return None
    return found[-1] if lowest else found[0]
