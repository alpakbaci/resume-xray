"""Command-line entry point: `resume-xray`."""

import argparse
import sys

from resume_xray import __version__
from resume_xray.models import Document
from resume_xray.readers import UnsupportedFormat, read_document

REGION_TITLES = {
    "header": "Header (some ATSs skip this)",
    "footer": "Footer (some ATSs skip this)",
    "textbox": "Text boxes (some ATSs skip or misplace these)",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="resume-xray",
        description="See how an ATS reads your resume. Runs locally; nothing leaves your machine.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("resume", nargs="?", help="resume file (.pdf or .docx)")
    parser.add_argument("--job", metavar="FILE", help="job description as a text file")
    parser.add_argument("--raw", action="store_true", help="show the raw text an ATS would extract")
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
    print("Checks are not implemented yet. Use --raw to see the extracted text. See ROADMAP.md.")
    return 0


def format_raw(document: Document) -> str:
    pages = len(document.pages)
    count = f", {pages} page{'s' if pages != 1 else ''}" if document.kind == "pdf" else ""
    out = [f"{document.name} ({document.kind.upper()}{count})"]
    for page in document.pages:
        if document.kind == "pdf":
            out.append(f"\n── Page {page.number} · {page.char_count} characters ──")
            out.append(page.text or "(no text found on this page)")
        else:
            out.append("\n── Body ──")
            out.append(page.text or "(no text found in the body)")
            for region, title in REGION_TITLES.items():
                texts = [line.text for line in page.lines if line.region == region]
                if texts:
                    out.append(f"\n── {title} ──")
                    out.extend(texts)
    return "\n".join(out)
