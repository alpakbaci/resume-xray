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
    for strategy in ("stream", "position", "columns"):
        assert "Backend Developer" in page.readings[strategy]


def test_two_columns_are_not_merged_into_one_line(tmp_path):
    document = read_document(write_pdf(tmp_path / "cv.pdf", [TWO_COLUMN]))

    texts = [line.text for line in document.lines]
    assert "EXPERIENCE" in texts and "SKILLS" in texts
    assert "Backend Developer at Acme" in texts and "Python, Docker" in texts
    readings = document.pages[0].readings
    # Position order runs straight across both columns; column-aware order keeps them apart.
    assert "Backend Developer at Acme Python, Docker" in readings["position"]
    assert readings["columns"].splitlines() == [
        "EXPERIENCE", "Backend Developer at Acme", "Built REST APIs", "SKILLS", "Python, Docker", "PostgreSQL, Git",
    ]
    assert document.pages[0].gutter is not None


def test_tiny_shifted_bullet_stays_with_its_sentence(tmp_path):
    # Seen on a real resume: bullets drawn as 0.7 pt glyphs, about 6.7 pt below the line's top.
    pages = [[
        Text(50, 150, "\u2022", size=0.7),
        Text(58, 156, "Managed 2-4 concurrent projects", size=10),
        Text(50, 167, "\u2022", size=0.7),
        Text(58, 173, "Coordinated cross-functional teams", size=10),
    ]]
    document = read_document(write_pdf(tmp_path / "cv.pdf", pages))

    assert [line.text for line in document.lines] == [
        "\u2022 Managed 2-4 concurrent projects",
        "\u2022 Coordinated cross-functional teams",
    ]


def test_invisible_bullet_over_first_letter_comes_first(tmp_path):
    # Seen on a real resume: the visible bullet is a drawn shape; a 0.75 pt text bullet sits
    # over the first letter, lower than the line's top.
    pages = [[Text(58, 154, "\u2022", size=0.75), Text(58, 156, "Managed projects", size=10)]]
    document = read_document(write_pdf(tmp_path / "cv.pdf", pages))

    assert [line.text for line in document.lines] == ["\u2022 Managed projects"]


def test_word_is_not_split_where_the_font_changes(tmp_path):
    # Seen on a real resume: the İ of "TÜBİTAK" came from a different font subset.
    pages = [[Text(50, 100, "T\u00dcB", size=10, then="ITAK funded")]]
    document = read_document(write_pdf(tmp_path / "cv.pdf", pages))

    assert [line.text for line in document.lines] == ["T\u00dcBITAK funded"]


def test_page_without_text(tmp_path):
    document = read_document(write_pdf(tmp_path / "scan.pdf", [[]]))

    page = document.pages[0]
    assert page.char_count == 0
    assert page.readings["position"] == ""
    assert page.lines == []


def test_group_lines_splits_rows_at_wide_gaps_only():
    def word(text, x0, top):
        return Word(text, x0, top, x0 + 30, top + 10, 11, False)

    words = [word("left", 50, 100), word("right", 300, 101), word("near", 85, 100.5), word("next", 50, 120)]
    lines = group_lines(words, page=1, row_overlap=0.5, split_gap=15)

    assert [line.text for line in lines] == ["left near", "right", "next"]
