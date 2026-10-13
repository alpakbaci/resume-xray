"""FastAPI app serving the page and one analysis endpoint.

Privacy: the server listens on 127.0.0.1 only, accepts requests addressed to localhost only, keeps
uploads in memory and forgets them after answering, and tells the browser (Content-Security-Policy)
that the page may not load or send anything outside this server.
"""

import json
from dataclasses import asdict
from importlib.resources import files

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from resume_xray import __version__
from resume_xray.checks import run_checks
from resume_xray.match import match_job
from resume_xray.readers import UnsupportedFormat, read_bytes

MAX_UPLOAD_BYTES = 15 * 1024 * 1024
STATIC = files("resume_xray.web").joinpath("static")
SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
    "connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; "
    "frame-ancestors 'none'",
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
}

app = FastAPI(title="resume-xray", version=__version__, docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers.update(SECURITY_HEADERS)
    return response


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    short = ".".join(__version__.split(".")[:2])
    page = STATIC.joinpath("index.html").read_text(encoding="utf-8")
    return page.replace("{{short_version}}", short).replace("{{version}}", __version__)


@app.post("/api/analyze")
async def analyze(
    file: UploadFile = File(...),
    job: str = Form(""),
    title: str = Form(""),
    add: str = Form("[]"),
    remove: str = Form("[]"),
) -> dict:
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "too_large")
    try:
        document = read_bytes(data, file.filename or "")
    except UnsupportedFormat:
        raise HTTPException(400, "unsupported_type")
    except Exception:
        raise HTTPException(422, "unreadable_file")

    report = run_checks(document)
    added, removed = _terms(add), _terms(remove)
    match = None
    if job.strip() or added:
        match = match_job(document, job, report.section_lines, title.strip() or None, added, removed)

    result = asdict(report)
    result.pop("section_lines")
    result["verdict"] = report.verdict
    result["readings"] = {s: document.reading(s) for s in document.strategies}
    result["job_match"] = asdict(match) if match else None
    return result


def _terms(value: str) -> list[str]:
    try:
        terms = json.loads(value)
    except json.JSONDecodeError:
        raise HTTPException(400, "bad_terms")
    if not isinstance(terms, list) or not all(isinstance(t, str) for t in terms):
        raise HTTPException(400, "bad_terms")
    return terms
