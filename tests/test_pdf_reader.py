from pdfgen import Text, write_pdf

from resume_xray.models import Word
from resume_xray.readers import read_document
from resume_xray.readers.pdf import group_lines

SINGLE_COLUMN = [
    Text(50, 60, "Jane Doe", size=20, bold=True),
    Text(50, 85, "jane.doe@example.com  +90 555 123 45 67"),
    Text(50, 130, "EXPERIENCE", size=13, bold=True),
    Text(50, 150, "Backend Developer, Acme Corp, 01/2021 - Present"),
    Text(50, 166, "Built REST APIs in Python and PostgreSQL."),
]

TWO_COLUMN = [
    Text(50, 130, "EXPERIENCE", size=13, bold=True),
    Text(330, 130, "SKILLS", size=13, bold=True),
    Text(50, 150, "Backend Developer at Acme"),
    Text(330, 150, "Python, Docker"),
    Text(50, 166, "Built REST APIs"),
    Text(330, 166, "PostgreSQL, Git"),
]


def test_reads_lines_fonts_and_both_readers(tmp_path):
    document = read_document(write_pdf(tmp_path / "cv.pdf", [SINGLE_COLUMN]))

    assert document.kind == "pdf"
    page = document.pages[0]
    texts = [line.text for line in page.lines]
    assert texts[0] == "Jane Doe"
    assert "EXPERIENCE" in texts
    heading = next(line for line in page.lines if line.text == "EXPERIENCE")
    assert heading.bold and heading.font_size == 13
    assert not next(line for line in page.lines if line.text.startswith("Built")).bold
    assert page.char_count > 100
    assert "Backend Developer" in page.text
    assert "Backend Developer" in page.alt_text


def test_two_columns_are_not_merged_into_one_line(tmp_path):
    document = read_document(write_pdf(tmp_path / "cv.pdf", [TWO_COLUMN]))

    texts = [line.text for line in document.lines]
    assert "EXPERIENCE" in texts and "SKILLS" in texts
    assert "Backend Developer at Acme" in texts and "Python, Docker" in texts
    # A naive extraction runs straight across both columns, which is what the user should see.
    assert "Backend Developer at Acme Python, Docker" in document.pages[0].text


def test_page_without_text(tmp_path):
    document = read_document(write_pdf(tmp_path / "scan.pdf", [[]]))

    page = document.pages[0]
    assert page.char_count == 0
    assert page.text == ""
    assert page.lines == []


def test_group_lines_splits_rows_at_wide_gaps_only():
    def word(text, x0, top):
        return Word(text, x0, top, x0 + 30, top + 10, 11, False)

    words = [word("left", 50, 100), word("right", 300, 101), word("near", 85, 100.5), word("next", 50, 120)]
    lines = group_lines(words, page=1, row_tolerance=3, split_gap=15)

    assert [line.text for line in lines] == ["left near", "right", "next"]
