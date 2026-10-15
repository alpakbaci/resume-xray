"""Labels of the test resumes and how a report is compared with them (tests/fixtures/README.md)."""

import os
import tomllib
from pathlib import Path

SYNTHETIC = Path(__file__).parent / "fixtures" / "synthetic"
# Private resumes stay on the maintainer's computer and are never committed.
PRIVATE = Path(os.environ.get("RESUME_XRAY_PRIVATE", "~/resume-xray-private")).expanduser()


def labeled_resumes(*folders: Path) -> list[Path]:
    return sorted(
        p for folder in folders if folder.is_dir()
        for p in folder.iterdir()
        if p.suffix.lower() in (".pdf", ".docx") and label_path(p).exists()
    )


def label_path(resume: Path) -> Path:
    return resume.with_name(resume.name + ".toml")


def load_label(resume: Path) -> dict:
    return tomllib.loads(label_path(resume).read_text(encoding="utf-8"))


def compare(report, label: dict) -> list[str]:
    """Differences between a report and its label, as readable sentences; empty when they agree."""
    codes = {f.code for f in report.findings}
    problems = []
    if "verdict" in label and report.verdict != label["verdict"]:
        problems.append(f"verdict {report.verdict}, expected {label['verdict']}")
    problems += [f"missing finding {c}" for c in label.get("must_find", []) if c not in codes]
    problems += [f"unexpected finding {c}" for c in label.get("must_not_find", []) if c in codes]
    for code, strategies in label.get("affects", {}).items():
        found = next((f for f in report.findings if f.code == code), None)
        if found and not set(strategies) <= set(found.strategies):
            problems.append(f"{code} affects {list(found.strategies)}, expected at least {strategies}")
    for code, strategies in label.get("not_affects", {}).items():
        found = next((f for f in report.findings if f.code == code), None)
        if found and set(strategies) & set(found.strategies):
            problems.append(f"{code} affects {list(found.strategies)}, expected none of {strategies}")
    problems += [f"section {s} not recognized" for s in label.get("sections", []) if s not in report.sections]
    return problems
