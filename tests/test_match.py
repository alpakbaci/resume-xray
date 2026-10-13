import math

import pytest
from pdfgen import Text, write_pdf

from resume_xray.checks import run_checks
from resume_xray.match import _degree, analyze, detect_language, lower, match_job, parse_job
from resume_xray.models import Document, Page
from resume_xray.readers import read_document

JOB = """Senior Backend Developer

About Us
We use Slack and Notion every day.

Requirements
- 3+ years of experience with Python and Kubernetes
- Experience building REST APIs and managing deployments
- Bachelor's degree in Computer Engineering

Nice to have
- Terraform
"""


def resume(tmp_path, *lines):
    texts = [Text(50, 50, "Jane Doe", size=20, bold=True), Text(50, 75, "jane@example.com")]
    texts += [Text(50, 110 + 16 * i, line, size=13 if line.isupper() else 11, bold=line.isupper()) for i, line in enumerate(lines)]
    document = read_document(write_pdf(tmp_path / "cv.pdf", [texts]))
    return document, run_checks(document)


def test_normalization_keeps_technical_terms_and_drops_turkish_suffixes():
    tokens = [t.surface for t in analyze("Python'da C++, C#, .NET ve Node.js", "tr")]
    assert tokens == ["python", "c++", "c#", ".net", "ve", "node.js"]
    assert lower("IŞIK İzmir", "tr") == "ışık izmir"
    assert lower("IT Istanbul", "en") == "it istanbul"
    assert detect_language("Aranan nitelikler ve sorumluluklar için en az 3 yıl deneyim") == "tr"
    assert detect_language("You will work with the team on our product") == "en"


def test_job_sections_requirement_and_weight():
    job = parse_job(JOB)
    terms = {t.name: t for t in job.terms}

    assert job.title == "Senior Backend Developer"
    assert "Slack" not in terms and "Notion" not in terms
    assert terms["Python"].requirement == 1.0
    assert terms["Terraform"].requirement == 0.5
    assert terms["Python"].weight == pytest.approx(1 + math.log(2))


def test_preferred_cue_inside_requirements():
    job = parse_job("Requirements\n- Go experience is a plus\n- Java\n")
    terms = {t.name: t.requirement for t in job.terms}
    assert terms == {"Go": 0.5, "Java": 1.0}


def test_short_terms_need_matching_capitals():
    job = parse_job("Requirements\nR&D background, go-getter attitude, R and C programming\n")
    assert {t.name for t in job.terms} == {"R", "C"}


def test_match_levels_and_coverage(tmp_path):
    document, report = resume(
        tmp_path,
        "EXPERIENCE",
        "Backend Developer, Acme, 01/2020 - 06/2022",
        "Built REST APIs in Python, managed deployments on k8s",
        "Platform Engineer, Beta, 03/2022 - Present",
        "EDUCATION",
        "BSc Computer Engineering",
        "SKILLS",
        "Python, Docker",
    )
    match = match_job(document, JOB, report.section_lines)
    levels = {t.name: t.level for t in match.terms}

    assert levels["Python"] == "exact"
    assert levels["REST API"] == "exact"
    assert levels["Kubernetes"] == "synonym"
    assert levels["Terraform"] == "missing"
    python = next(t for t in match.terms if t.name == "Python")
    assert python.sections == ("EXPERIENCE", "SKILLS")
    assert match.preferred_coverage == 0
    assert 0 < match.required_coverage < 1
    assert match.title_match is None
    assert match.years_required == 3
    assert match.years_in_resume >= 6.5  # 01/2020 to today, overlap counted once
    assert (match.degree_required, match.degree_in_resume) == ("Bachelor", "Bachelor")


def test_word_form_is_partial(tmp_path):
    document, report = resume(tmp_path, "EXPERIENCE", "Led roadmap planning", "SKILLS", "Jira")
    match = match_job(document, "Requirements\nOwn the roadmaps\n", report.section_lines)
    [term] = match.terms
    assert term.level == "word_form" and term.resume_wording == "roadmap"
    assert match.required_coverage == 0.5


def test_term_lost_in_a_reading():
    page = Page(1, 595, 842, readings={"stream": "TÜB İ TAK project", "position": "TÜBİTAK project", "columns": "TÜBİTAK project"})
    document = Document("cv.pdf", "pdf", [page])
    match = match_job(document, "Requirements\nTÜBİTAK projects\n", {})
    assert match.terms == []  # not in the skill dictionary and not technical-looking

    page.readings = {"stream": "TÜB İ TAK2024", "position": "TÜBİTAK2024", "columns": "TÜBİTAK2024"}
    match = match_job(document, "Requirements\nTÜBİTAK2024 projects\n", {})
    [term] = match.terms
    assert term.level == "exact" and term.lost_in == ("stream",)


@pytest.mark.parametrize(
    ("text", "lowest", "expected"),
    [
        ("Üniversitelerin ilgili bölümlerinden lisans veya yüksek lisans mezunu", True, "Bachelor"),
        ("MSc. Mechatronics, BSc. Mechatronics", False, "Master"),
        ("Yüksek Lisans, Yıldız Teknik Üniversitesi", False, "Master"),
        ("PhD or Master's degree", True, "Master"),
    ],
)
def test_degrees(text, lowest, expected):
    assert _degree(text, lowest) == expected
