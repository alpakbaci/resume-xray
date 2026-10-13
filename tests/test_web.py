import re
from importlib.resources import files

import pytest
from fastapi.testclient import TestClient
from pdfgen import Text, write_pdf

from resume_xray.web.app import app

client = TestClient(app)


@pytest.fixture
def pdf(tmp_path):
    texts = [
        Text(50, 50, "Jane Doe", size=20, bold=True),
        Text(50, 75, "jane@example.com"),
        Text(50, 110, "EXPERIENCE", size=13, bold=True),
        Text(50, 130, "Backend Developer, 2020 - 2023, Python"),
    ]
    return write_pdf(tmp_path / "cv.pdf", [texts]).read_bytes()


def test_page_has_strict_security_headers():
    response = client.get("/")
    assert response.status_code == 200
    policy = response.headers["content-security-policy"]
    assert "default-src 'self'" in policy and "connect-src 'self'" in policy
    assert response.headers["cache-control"] == "no-store"


def test_assets_never_load_anything_from_the_internet():
    static = files("resume_xray.web").joinpath("static")
    for name in ("index.html", "app.css", "app.js", "i18n.js"):
        text = static.joinpath(name).read_text(encoding="utf-8")
        assert not re.search(r"https?://|//cdn|@import", text), name


def test_requests_for_other_hosts_are_refused():
    assert client.get("/", headers={"host": "evil.example"}).status_code == 400


def test_analyze_resume_and_job(pdf):
    response = client.post(
        "/api/analyze",
        files={"file": ("cv.pdf", pdf, "application/pdf")},
        data={"job": "Requirements\nPython and Docker\n", "add": '["Scrum"]', "remove": "[]"},
    )
    data = response.json()

    assert response.status_code == 200
    assert data["document"] == "cv.pdf"
    assert set(data["readings"]) == {"stream", "position", "columns"}
    levels = {t["name"]: t["level"] for t in data["job_match"]["terms"]}
    assert levels == {"Python": "exact", "Docker": "missing", "Scrum": "missing"}
    assert "section_lines" not in data


def test_analyze_without_job_has_no_match(pdf):
    data = client.post("/api/analyze", files={"file": ("cv.pdf", pdf, "application/pdf")}).json()
    assert data["job_match"] is None


@pytest.mark.parametrize(
    ("name", "content", "status", "detail"),
    [
        ("cv.txt", b"hello", 400, "unsupported_type"),
        ("cv.pdf", b"not a pdf", 422, "unreadable_file"),
    ],
)
def test_bad_files(name, content, status, detail):
    response = client.post("/api/analyze", files={"file": (name, content)})
    assert response.status_code == status and response.json()["detail"] == detail
