"""Run every labeled resume and report what the checks measured and how it compares with the labels.

    python tools/calibrate.py                    # synthetic fixtures
    python tools/calibrate.py ~/resume-xray-private   # also your private resumes (never committed)

For each resume it prints the verdict, the findings with the readings they affect, and the raw
measurements behind the thresholds (order similarity per reading, gutter, bullet size ratio), so
that a threshold can be justified from the numbers. Labels are the `.toml` files next to each
resume, e.g. `cv.pdf.toml` (see tests/fixtures/README.md).
"""

import sys
from pathlib import Path
from statistics import median

from rapidfuzz.distance import Indel

from resume_xray.checks import ROUND_BULLETS, mixes_columns, run_checks
from resume_xray.config import load_weights
from resume_xray.readers import read_document
from resume_xray.text import tokens

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from labels import SYNTHETIC, compare, label_path, load_label  # noqa: E402


def resumes(folders: list[Path]) -> list[Path]:
    return sorted(p for folder in folders for p in folder.iterdir() if p.suffix.lower() in (".pdf", ".docx"))


def measurements(document) -> list[str]:
    out = []
    for page in document.pages:
        if document.kind != "pdf":
            break
        reference = tokens(page.readings["columns"])
        sims = []
        for strategy in ("stream", "position"):
            text = page.readings[strategy]
            if text is None or not reference:
                continue
            sim = Indel.normalized_similarity(tokens(text), reference)
            mixed = page.gutter is not None and mixes_columns(page, text)
            sims.append(f"{strategy} {sim:.3f}{' mixed' if mixed else ''}")
        gutter = f"gutter {page.gutter.x1 - page.gutter.x0:.0f}pt" if page.gutter else "no gutter"
        ratios = [l.sizes[0] / median(l.sizes[1:]) for l in page.lines if l.text[:1] in ROUND_BULLETS and len(l.sizes) > 1]
        bullets = f", bullet ratio {min(ratios):.2f}" if ratios else ""
        out.append(f"p{page.number}: {gutter}, order {', '.join(sims) or '-'}{bullets}")
    return out


def main(args: list[str]) -> int:
    weights = load_weights()["parseability"]
    print(f"agreement_order_max = {weights['agreement_order_max']}, bullet_size_ratio = {weights['bullet_size_ratio']}\n")
    folders = [SYNTHETIC] + [Path(a).expanduser() for a in args]
    failures = 0
    for resume in resumes(folders):
        document = read_document(resume)
        report = run_checks(document)
        label = load_label(resume) if label_path(resume).exists() else None
        findings = ", ".join(f"{f.code}[{'/'.join(f.strategies)}]" if f.strategies else f.code for f in report.findings)
        print(f"{resume.name}: {report.verdict}  {findings or 'no findings'}")
        for line in measurements(document):
            print("   ", line)
        if label is None:
            print("    (no label)")
            continue
        problems = compare(report, label)
        traits = [k for k, v in label.get("answers", {}).items() if v == "yes" and k in ("photo", "wide_gaps", "unusual_fonts", "icons")]
        if traits:
            print("    traits:", ", ".join(traits))
        failures += bool(problems)
        for problem in problems:
            print("    ✖", problem)
    print(f"\n{failures} labeled resume(s) disagree with their labels.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
