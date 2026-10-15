"""Labels of the test resumes and how a report is compared with them (tests/fixtures/README.md)."""

import os
import tomllib
from pathlib import Path

SYNTHETIC = Path(__file__).parent / "fixtures" / "synthetic"
# Private resumes stay on the maintainer's computer and are never committed. They are tested only
# when RESUME_XRAY_PRIVATE names their folder, so a routine `pytest` never reveals results to someone
# who is still labeling them blind.
PRIVATE_DEFAULT = Path("~/resume-xray-private").expanduser()
PRIVATE = Path(os.environ["RESUME_XRAY_PRIVATE"]).expanduser() if os.environ.get("RESUME_XRAY_PRIVATE") else None


def is_resume(path: Path) -> bool:
    """A PDF or DOCX, but not the lock file Word ("~$name.docx") or LibreOffice (".~lock") keeps
    next to an open document."""
    return path.suffix.lower() in (".pdf", ".docx") and not path.name.startswith(("~$", ".~lock", "."))


def labeled_resumes(*folders: Path) -> list[Path]:
    return sorted(
        p for folder in folders if folder.is_dir()
        for p in folder.iterdir()
        if is_resume(p) and label_path(p).exists()
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
