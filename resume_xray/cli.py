"""Command-line entry point: `resume-xray`."""

import argparse
import json
import sys
from dataclasses import asdict

from resume_xray import __version__
from resume_xray.checks import run_checks
from resume_xray.match import MatchReport, match_job
from resume_xray.models import STRATEGY_NAMES, Document
from resume_xray.readers import UnsupportedFormat, read_document
from resume_xray.report import Report
from resume_xray.text import decode_text

STRATEGY_SOURCES = {
    "stream": "pypdf; like Apache Tika and PDFBox with default settings",
    "position": "pdfplumber; like PDFBox/Tika with sortByPosition",
    "columns": "resume-xray; like pdftotext and column-aware parsers",
    "full": "headers, body, text boxes, footers",
    "body": "body paragraphs and tables only",
}
SYMBOLS = {"critical": "✖", "warning": "⚠", "info": "ℹ"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="resume-xray",
        description="See how an ATS reads your resume. Runs locally; nothing leaves your machine.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("resume", nargs="?", help="resume file (.pdf or .docx)")
    parser.add_argument("--job", metavar="FILE", help="job description as a text file")
    parser.add_argument("--title", help="job title, if the job description does not start with it")
    parser.add_argument("--raw", action="store_true", help="show the text each reading strategy extracts")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.resume:
        parser.print_help()
        return 0
    try:
        document = read_document(args.resume)
    except (UnsupportedFormat, FileNotFoundError) as error:
        print(f"resume-xray: {error}", file=sys.stderr)
        return 2
    if args.raw:
        print(format_raw(document))
        return 0
    report = run_checks(document)
    match = None
    if args.job:
        try:
            with open(args.job, "rb") as f:
                job_text = decode_text(f.read())
        except OSError as error:
            print(f"resume-xray: {error}", file=sys.stderr)
            return 2
        match = match_job(document, job_text, report.section_lines, args.title)
    if args.json:
        data = {**asdict(report), "verdict": report.verdict}
        data.pop("section_lines", None)
        if match:
            data["job_match"] = asdict(match)
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(format_report(report))
        if match:
            print(format_match(match))
    return 0


def format_report(report: Report) -> str:
    count = f", {report.pages} page{'s' if report.pages != 1 else ''}" if report.kind == "pdf" else ""
    tally = {s: sum(f.severity == s for f in report.findings) for s in SYMBOLS}
    out = [
        f"{report.document} ({report.kind.upper()}{count})",
        f"Parseability: {report.verdict} — {tally['critical']} critical, {tally['warning']} warnings, "
        f"{tally['info']} info",
    ]
    for finding in report.findings:
        out.append(f"\n{SYMBOLS[finding.severity]} {finding.title}  [{finding.check}]")
        if finding.strategies:
            out.append(f"  Affects: {', '.join(STRATEGY_NAMES[s] for s in finding.strategies)}")
        if finding.pages:
            out.append(f"  Pages: {', '.join(map(str, finding.pages))}")
        out.append(f"  {finding.detail}")
        if finding.examples:
            out.append(f"  Examples: {', '.join(finding.examples)}")
        if finding.fix:
            out.append(f"  Fix: {finding.fix}")
    out.append("\nSections found: " + (", ".join(report.sections.values()) or "none"))
    out.append("Contact found: " + (", ".join(report.fields.values()) or "none"))
    out.append("\nSee what each ATS reading strategy extracts: resume-xray FILE --raw")
    return "\n".join(out)


LEVEL_SYMBOLS = {"exact": "✔", "word_form": "≈", "synonym": "≈", "missing": "✖"}


def format_match(match: MatchReport) -> str:
    out = ["\n" + "─" * 60, f"Job match: {match.job_title or '(untitled job description)'}"]
    for kind, coverage in (("required", match.required_coverage), ("preferred", match.preferred_coverage)):
        terms = [t for t in match.terms if t.kind == kind]
        if not terms:
            continue
        found = sum(t.level != "missing" for t in terms)
        out.append(f"\n{kind.capitalize()} terms: {coverage:.0%} covered ({found} of {len(terms)} found)")
        for t in terms:
            line = f"  {LEVEL_SYMBOLS[t.level]} {t.job_wording}"
            if t.level == "exact":
                line += f"  — {', '.join(t.sections)}" if t.sections else ""
            elif t.level == "word_form":
                line += f'  — resume says "{t.resume_wording}"; a search for the job\'s word may miss it'
            elif t.level == "synonym":
                line += f'  — resume says "{t.resume_wording}"; also write "{t.job_wording}"'
            if t.lost_in:
                line += f"  (not found in {', '.join(STRATEGY_NAMES[s] for s in t.lost_in)})"
            out.append(line)
    out.append("")
    if not match.job_title:
        out.append('Job title: not found in the job description; pass it with --title "..."')
    else:
        out.append(
            f'Job title: found in "{match.title_match}"' if match.title_match
            else f'Job title: "{match.job_title}" does not appear in the resume'
        )
    if match.years_required:
        have = f"{match.years_in_resume:g} years" if match.years_in_resume is not None else "no parseable date ranges"
        mark = "✔" if match.years_in_resume is not None and match.years_in_resume >= match.years_required else "✖"
        out.append(f"Experience: job asks {match.years_required}+ years, resume shows {have} {mark}")
    if match.degree_required:
        order = ["Bachelor", "Master", "PhD"]
        ok = match.degree_in_resume and order.index(match.degree_in_resume) >= order.index(match.degree_required)
        out.append(f"Degree: job asks {match.degree_required}, resume shows {match.degree_in_resume or 'none'} {'✔' if ok else '✖'}")
    return "\n".join(out)


def format_raw(document: Document) -> str:
    pages = len(document.pages)
    count = f", {pages} page{'s' if pages != 1 else ''}" if document.kind == "pdf" else ""
    out = [f"{document.name} ({document.kind.upper()}{count})"]
    for strategy in document.strategies:
        out.append(f"\n══ {STRATEGY_NAMES[strategy].capitalize()} ({STRATEGY_SOURCES[strategy]}) ══")
        for page in document.pages:
            if document.kind == "pdf":
                out.append(f"── Page {page.number} · {page.char_count} characters ──")
            text = page.readings.get(strategy)
            out.append(text if text else "(this reader could not read the file)" if text is None else "(no text)")
    return "\n".join(out)
