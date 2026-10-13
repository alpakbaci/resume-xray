"""Convert a resume file into a Document."""

from io import BytesIO
from pathlib import Path

from resume_xray.models import Document


class UnsupportedFormat(ValueError):
    pass


def read_document(path: str | Path) -> Document:
    path = Path(path)
    return read_bytes(path.read_bytes() if path.suffix.lower() in (".pdf", ".docx") else b"", path.name)


def read_bytes(data: bytes, name: str) -> Document:
    """Read a resume from memory; nothing is written to disk."""
    suffix = Path(name).suffix.lower()
    if suffix == ".pdf":
        from resume_xray.readers.pdf import read_pdf

        return read_pdf(BytesIO(data), name)
    if suffix == ".docx":
        from resume_xray.readers.docx import read_docx

        return read_docx(BytesIO(data), name)
    if suffix == ".doc":
        raise UnsupportedFormat("Old .doc files are not supported; save the file as .docx or .pdf.")
    raise UnsupportedFormat(f"Unsupported file type {suffix or '(none)'}; use .pdf or .docx.")
