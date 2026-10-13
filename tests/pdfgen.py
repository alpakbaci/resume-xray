"""Builds small text PDFs for tests, with no extra dependency.

Uses the standard Helvetica fonts with WinAnsi encoding, so text must fit in cp1252. Positions are in points from the
top-left corner of an A4 page; `y` is the text baseline.
"""

from dataclasses import dataclass
from pathlib import Path

A4 = (595.0, 842.0)


@dataclass
class Text:
    x: float
    y: float
    text: str
    size: float = 11
    bold: bool = False
    # Text continuing right after `text` in the other font (regular <-> bold).
    then: str = ""


def write_pdf(path: Path, pages: list[list[Text]]) -> Path:
    width, height = A4
    objects: list[bytes] = []

    def add(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    catalog = add(b"")  # filled in once the page tree number is known
    regular = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    bold = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
    tree = add(b"")
    page_ids = []
    for texts in pages:
        stream = b"".join(
            b"BT /%s %g Tf %g %g Td (%s) Tj /%s %g Tf (%s) Tj ET\n"
            % (
                b"F2" if t.bold else b"F1", t.size, t.x, height - t.y, _escape(t.text),
                b"F1" if t.bold else b"F2", t.size, _escape(t.then),
            )
            for t in texts
        )
        content = add(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream))
        page_ids.append(
            add(
                b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %g %g] /Contents %d 0 R "
                b"/Resources << /Font << /F1 %d 0 R /F2 %d 0 R >> >> >>"
                % (tree, width, height, content, regular, bold)
            )
        )
    objects[catalog - 1] = b"<< /Type /Catalog /Pages %d 0 R >>" % tree
    kids = b" ".join(b"%d 0 R" % i for i in page_ids)
    objects[tree - 1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (kids, len(page_ids))

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (number, body)
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, catalog, xref)
    path.write_bytes(bytes(out))
    return path


def _escape(text: str) -> bytes:
    return text.encode("cp1252").replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")
