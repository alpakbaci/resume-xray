"""Blind labeling of private test resumes.

    python tools/label.py                       # ~/resume-xray-private
    python tools/label.py path/to/folder

Opens a local page that shows each resume (PDF pages as images; DOCX opens in Word) next to
questions anyone can answer by looking at the document. It never runs resume-xray and never shows
its results, so the labels are written before the tool's answer is known. Answers are saved as
`<file>.toml` next to the resume in the format of tests/fixtures/README.md.

Only questions about what is visible are asked. Effects that need extraction to see (misplaced
bullets, split words) are left to be measured against Apache Tika.
"""

import html
import io
import subprocess
import sys
import tomllib
import webbrowser
from datetime import date
from pathlib import Path
from threading import Timer

import pypdfium2
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

FOLDER = Path(sys.argv[1] if len(sys.argv) > 1 else "~/resume-xray-private").expanduser()
CORE = {"experience": "Experience / İş deneyimi", "education": "Education / Eğitim", "skills": "Skills / Yetenekler"}
SOURCES = ["Canva", "Word", "Google Docs", "LinkedIn", "Job site (Kariyer.net, Indeed...)", "LaTeX / Overleaf",
           "Other web builder", "Scanned / photo", "Unknown"]

QUESTIONS = [
    ("selectable", "Can you select and copy the text in a PDF viewer? (Metni seçip kopyalayabiliyor musunuz?)",
     [("yes", "Yes"), ("no", "No, it is an image")], "pdf"),
    ("layout", "How is the main content laid out? (Ana içerik nasıl yerleşmiş?)",
     [("single", "One column"), ("columns", "Two columns or a sidebar"), ("grid", "Boxes / table-like grid")], "pdf"),
    ("unusual_headings", "Are any section headings unusual, not like Experience, Education, Skills, Projects, Languages? (Alışılmadık başlık var mı?)",
     [("no", "No"), ("yes", "Yes")], "all"),
    ("email", "Is an email address written out as text? (E-posta adresi metin olarak yazılı mı?)",
     [("body", "Yes, on the page"), ("header", "Only in the Word header or footer"), ("no", "No")], "all"),
    ("linkedin", "LinkedIn address (LinkedIn adresi)",
     [("text", "Written out as text"), ("link", "Only a clickable word or icon"), ("none", "Not there")], "all"),
    ("vague_dates", "Any dates written with a season or quarter, like Summer 2021, Q3 2020, Yaz 2021? (Mevsim/çeyrekle yazılmış tarih var mı?)",
     [("no", "No"), ("yes", "Yes")], "all"),
    ("text_boxes", "Is any text inside Word text boxes? (Word metin kutusu içinde metin var mı?)",
     [("no", "No"), ("yes", "Yes")], "docx"),
]

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


def resumes() -> list[Path]:
    return sorted(p for p in FOLDER.iterdir() if p.suffix.lower() in (".pdf", ".docx"))


def resume(name: str) -> Path:
    for path in resumes():
        if path.name == name:
            return path
    raise HTTPException(404)


def label_file(path: Path) -> Path:
    return path.with_name(path.name + ".toml")


def saved_answers(path: Path) -> dict:
    if not label_file(path).exists():
        return {}
    return tomllib.loads(label_file(path).read_text(encoding="utf-8")).get("answers", {})


def page(title: str, body: str) -> str:
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>{html.escape(title)}</title><style>
body{{font:15px/1.5 system-ui,sans-serif;margin:0;background:#f6f5f1;color:#1e2a47}}
header{{padding:12px 20px;background:#294074;color:#fff}} header a{{color:#fceea7}}
.wrap{{display:grid;grid-template-columns:minmax(0,1.2fr) minmax(320px,1fr);gap:20px;padding:20px}}
.pages img{{width:100%;border:1px solid #ccc;margin-bottom:12px;background:#fff}}
fieldset{{border:none;border-top:1px solid #ddd;margin:0;padding:12px 0}} legend{{font-weight:600;padding:0}}
label{{display:block;margin:4px 0;cursor:pointer}} textarea{{width:100%;min-height:60px}}
button{{font:inherit;padding:8px 16px;background:#294074;color:#fff;border:none;border-radius:6px;cursor:pointer}}
li{{margin:6px 0}} .done{{color:#3f9e6e}} .todo{{color:#d72f2f}} form{{position:sticky;top:10px}}
</style></head><body><header><a href="/">All resumes</a> · {html.escape(title)}</header>{body}</body></html>"""


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    items = []
    for path in resumes():
        done = label_file(path).exists()
        items.append(f'<li><a href="/label/{html.escape(path.name)}">{html.escape(path.name)}</a> '
                     f'<span class="{"done" if done else "todo"}">{"labeled" if done else "not labeled"}</span></li>')
    intro = ("<p>Answer by looking at each resume. resume-xray's results are not shown here on purpose: "
             "label first, then compare with <code>python tools/calibrate.py ~/resume-xray-private</code>.</p>")
    return page(f"Blind labeling ({FOLDER})", f'<div style="padding:20px">{intro}<ol>{"".join(items) or "<li>Put PDF or DOCX files in the folder.</li>"}</ol></div>')


@app.get("/page/{name}/{number}.png")
def page_image(name: str, number: int) -> Response:
    document = pypdfium2.PdfDocument(str(resume(name)))
    if not 0 <= number < len(document):
        raise HTTPException(404)
    buffer = io.BytesIO()
    document[number].render(scale=1.6).to_pil().save(buffer, "PNG")
    return Response(buffer.getvalue(), media_type="image/png")


@app.get("/open/{name}")
def open_file(name: str) -> RedirectResponse:
    subprocess.run(["open", str(resume(name))], check=False)
    return RedirectResponse(f"/label/{name}", status_code=303)


@app.get("/label/{name}", response_class=HTMLResponse)
def label_form(name: str) -> str:
    path = resume(name)
    kind = path.suffix.lower().lstrip(".")
    answers = saved_answers(path)
    if kind == "pdf":
        count = len(pypdfium2.PdfDocument(str(path)))
        view = "".join(f'<img src="/page/{html.escape(name)}/{i}.png" alt="Page {i + 1}">' for i in range(count))
    else:
        view = f'<p><a href="/open/{html.escape(name)}">Open in Word</a> and look at the document there.</p>'

    fields = []
    for key, question, options, applies in QUESTIONS:
        if applies not in ("all", kind):
            continue
        radios = "".join(
            f'<label><input type="radio" name="{key}" value="{v}" required {"checked" if answers.get(key) == v else ""}> {text}</label>'
            for v, text in options
        )
        fields.append(f"<fieldset><legend>{question}</legend>{radios}</fieldset>")
    checks = "".join(
        f'<label><input type="checkbox" name="sections" value="{k}" {"checked" if k in answers.get("sections", []) else ""}> {t}</label>'
        for k, t in CORE.items()
    )
    fields.insert(2, f"<fieldset><legend>Which sections have a clearly visible heading? (Hangi bölümlerin görünür bir başlığı var?)</legend>{checks}</fieldset>")
    sources = "".join(f'<option {"selected" if answers.get("source") == s else ""}>{s}</option>' for s in SOURCES)
    fields.append(f'<fieldset><legend>Made with (Ne ile yapılmış?)</legend><select name="source">{sources}</select></fieldset>')
    langs = "".join(f'<label><input type="radio" name="language" value="{v}" required {"checked" if answers.get("language") == v else ""}> {v}</label>' for v in ("en", "tr", "other"))
    fields.append(f"<fieldset><legend>Language (Dil)</legend>{langs}</fieldset>")
    fields.append(f'<fieldset><legend>Anything notable? (Not)</legend><textarea name="comment">{html.escape(answers.get("comment", ""))}</textarea></fieldset>')
    form = f'<form method="post">{"".join(fields)}<p><button type="submit">Save and next</button></p></form>'
    return page(name, f'<div class="wrap"><div class="pages">{view}</div>{form}</div>')


@app.post("/label/{name}")
async def save_label(name: str, request: Request) -> RedirectResponse:
    path = resume(name)
    form = await request.form()
    answers = {key: form.get(key) for key, *_ in QUESTIONS if form.get(key)}
    answers.update(sections=form.getlist("sections"), source=form.get("source", "Unknown"),
                   language=form.get("language", ""), comment=form.get("comment", "").strip())
    label_file(path).write_text(to_toml(build_label(answers, path.suffix.lower())), encoding="utf-8")
    remaining = [p for p in resumes() if not label_file(p).exists()]
    return RedirectResponse(f"/label/{remaining[0].name}" if remaining else "/", status_code=303)


def build_label(a: dict, suffix: str) -> dict:
    """Turn visible facts into expectations (tests/fixtures/README.md)."""
    find, avoid, affects = [], [], {}
    pdf = suffix == ".pdf"

    def expect(condition: bool, code: str) -> None:
        (find if condition else avoid).append(code)

    if pdf:
        expect(a.get("selectable") == "no", "no_text_layer")
        if a.get("selectable") == "yes":
            if a.get("layout") in ("columns", "grid"):
                find.append("columns_scramble")
                affects["columns_scramble"] = ["position"]  # position sorting interleaves columns [Tika docs]
            elif a.get("layout") == "single":
                avoid.append("columns_scramble")
    else:
        expect(a.get("email") == "header", "contact_in_header")
        expect(a.get("text_boxes") == "yes", "text_boxes")
    expect(a.get("unusual_headings") == "yes", "heading_unknown")
    expect(a.get("email") == "no", "no_email")
    expect(a.get("linkedin") == "link", "linkedin_hidden")
    expect(a.get("vague_dates") == "yes", "vague_dates")
    if a.get("selectable") != "no":
        missing = [s for s in CORE if s not in a["sections"]]
        expect(bool(missing), "section_missing")
    note = (f"Labeled blind, before running resume-xray, on {date.today().isoformat()}. "
            f"Made with {a['source']}; language {a['language']}." + (f" {a['comment']}" if a["comment"] else ""))
    label = {"must_find": find, "must_not_find": avoid, "sections": a["sections"], "note": note}
    if affects:
        label["affects"] = affects
    label["answers"] = a
    return label


def to_toml(label: dict) -> str:
    def value(v):
        if isinstance(v, list):
            return "[" + ", ".join(value(x) for x in v) + "]"
        return '"' + str(v).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ") + '"'

    lines = [f"{k} = {value(v)}" for k, v in label.items() if not isinstance(v, dict)]
    for k, v in label.items():
        if isinstance(v, dict):
            lines.append(f"\n[{k}]")
            lines += [f"{key} = {value(val)}" for key, val in v.items()]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    FOLDER.mkdir(parents=True, exist_ok=True)
    port = 8766
    print(f"Labeling {FOLDER} at http://127.0.0.1:{port}  (Ctrl+C to stop)")
    Timer(1.0, webbrowser.open, args=(f"http://127.0.0.1:{port}",)).start()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
