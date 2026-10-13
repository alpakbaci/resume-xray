"""Convert a resume file into a Document."""

from pathlib import Path

from resume_xray.models import Document


class UnsupportedFormat(ValueError):
    pass


def read_document(path: str | Path) -> Document:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        from resume_xray.readers.pdf import read_pdf

        return read_pdf(path)
    if suffix == ".docx":
        from resume_xray.readers.docx import read_docx

        return read_docx(path)
    if suffix == ".doc":
        raise UnsupportedFormat("Old .doc files are not supported; save the file as .docx or .pdf.")
    raise UnsupportedFormat(f"Unsupported file type {suffix or '(none)'}; use .pdf or .docx.")
