"""Command-line entry point: `ats-checker`."""

import argparse

from ats_checker import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ats-checker",
        description="See how an ATS reads your resume. Runs locally; nothing leaves your machine.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("resume", nargs="?", help="resume file (.pdf or .docx)")
    parser.add_argument("--job", metavar="FILE", help="job description as a text file")
    return parser


def main(argv: list[str] | None = None) -> int:
    build_parser().parse_args(argv)
    print("ats-checker is under development; analysis is not implemented yet. See ROADMAP.md.")
    return 0
