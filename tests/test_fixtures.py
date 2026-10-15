"""Every labeled resume must agree with its label. Private resumes run only where they exist."""

import pytest
from labels import PRIVATE, SYNTHETIC, compare, labeled_resumes, load_label

from resume_xray.checks import run_checks
from resume_xray.readers import read_document

RESUMES = labeled_resumes(SYNTHETIC, PRIVATE)


def test_synthetic_set_is_labeled():
    assert len(labeled_resumes(SYNTHETIC)) >= 20


@pytest.mark.parametrize("resume", RESUMES, ids=lambda p: p.name)
def test_resume_matches_label(resume):
    report = run_checks(read_document(resume))
    assert compare(report, load_label(resume)) == []
