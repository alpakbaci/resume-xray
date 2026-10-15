# Algorithm

[Türkçe](ALGORITHM.tr.md)

This document explains how resume-xray analyzes a resume, why each computation is done, and the
justification for every threshold and weight it uses. All constants in the code live in
`resume_xray/config/weights.toml` under the names used in this document.

> **Status:** The values below are justified **starting values**. They will be updated as they
> are calibrated against the test set, and every change will be recorded here
> (see [Calibration](#5-calibration)).

---

## 1. What we measure, and what we don't

In commercial ATSs (Workday, Greenhouse, Taleo, Lever…) there are three real reasons an
application goes unseen:

1. **Parsing failure:** sections get lost or scrambled when the document is converted to text.
2. **Not showing up in search:** recruiters search by skill or job title; if the term is not in
   the resume, the application never appears in the results.
3. **Knockout questions:** questions on the application form such as work authorization or
   years of experience (unrelated to the resume text). In Oracle Taleo, for example, "a candidate
   not meeting the required response can be instantly exited from the application process" [1].

resume-xray measures **points 1 and 2**. It does not measure:

- Whether you will be hired, or "the score an ATS would give you". No ATS vendor publishes such a
  score; a tool claiming to reproduce one is guessing.
- The claim that "75% of resumes are rejected by ATS" is a **myth**. It traces back to a 2012 sales
  pitch by Preptel, a resume-optimization company that shut down in 2013, and no methodology was
  ever published [2].

### No single score

Results are not given as a single "73% match" number. Adding unrelated findings (a font problem,
a missing skill, a column layout) with arbitrary weights cannot be justified and hides critical
failures inside an average. Instead, two separate questions are answered:

| Question | Answer format | Rule |
|---|---|---|
| Can my document be parsed? | `OK` / `Risky` / `Unreadable` | The worst finding wins |
| Will I be found for this job? | Separate coverage for required and preferred terms | Weighted coverage (section 3) |

### Realistic, not flattering

resume-xray reports what ATS readers actually get, not a cleaned-up version. When a document is
read correctly only by a smarter reader than an ATS may use, the problem is still reported. Any
statement here about how ATSs or text extractors behave cites a source in
[References](#references); statements based on our own measurements say so.

### How ATSs read a PDF

Which text extractor a given commercial ATS uses is not public, so resume-xray does not pretend to
know. Instead it simulates the three reading strategies used by widely deployed extractors:

| Strategy | What it does | Documented examples | Simulated with |
|---|---|---|---|
| **Content-stream order** | Text in the order it is written inside the PDF file | Apache PDFBox and Apache Tika by default ("The default is to not sort by position" [3]; `sortByPosition` defaults to `false` [4]); `pdftotext -raw` [5] | `pypdf` |
| **Position order** | Text sorted top to bottom, left to right | PDFBox/Tika with `sortByPosition` on, which "can interleave columns" [4] | `pdfplumber` plain text |
| **Column-aware reading order** | Columns detected first, then read one by one | `pdftotext` default, which tries to "undo" physical layout such as columns [5]; Textkernel's parser, which detects column separators with a trained model [6] | Our own line and gutter detection (2.0, 2.3) |

For DOCX, the question is not order but which parts are read. Word stores headers, footers and
text boxes apart from the body paragraphs, so resume-xray compares two readings:

| Strategy | What it reads | Basis |
|---|---|---|
| **All document parts** | Headers, body, tables, text boxes, footers | What full extractors return, e.g. mammoth reads text boxes as "a separate paragraph that appears after the paragraph containing the text box" [8] |
| **Body paragraphs only** | Body paragraphs and tables | What `python-docx`'s `document.paragraphs` and `document.tables` return (our observation) |

A problem that breaks some strategies is a **warning** ("some ATSs"); a problem that breaks every
strategy is **critical**. Each finding names the strategies it affects.

---

## 2. Parseability

Each check produces a **severity**: `critical`, `warning` or `info`. There are no weights, only
thresholds.

- Any `critical` finding → **Unreadable**
- No `critical`, at least one `warning` → **Risky**
- Otherwise → **OK**

### 2.0 Reading the document (`row_overlap_min = 0.5`, `word_gap_pt = 3`)

Both formats are converted into one shared representation: lines of text with their page, font
size, boldness and region (body, header, footer, table, text box). PDF lines also carry their
position in points and the visual row they belong to. Each page also keeps the full text of every
reading strategy, so that checks can compare them.

**PDF words.** `pdfplumber` gives every character with its box, font and size. Characters are
joined into words in content-stream order. A word ends at whitespace, at a horizontal gap wider
than 3 points, when the text moves back to the left, or when the next character does not overlap
the word vertically by at least half of the smaller height (the same overlap rule as rows, below).
Font and size never end a word, and a round bullet is always a word of its own. A word counts as
bold when most of its characters come from a font whose name contains Bold, Black, Heavy, Semibold
or Demi.

*Justification:* Letters inside a word touch (gap about 0); a space is either a space character or
a gap of a quarter of the font size or more. 3 points is the default `x_tolerance` of `pdfplumber`.
*Found on real and generated resumes:* a letter taken from another font sits at another height. On
one resume the İ of "TÜBİTAK" came from a separate font subset; in a Chrome-printed Turkish resume
the "ı" of "Yılmaz" fell back to Helvetica and sat 5 points lower than its word. Splitting words at
font changes, or by top edge, broke both words ("TÜB İ TAK", "Y ı lmaz").

**PDF rows and lines.** A word joins a visual row when its vertical extent overlaps the row's by at
least half of the smaller of the two heights:

```
overlap(word, row) / min(height(word), height(row)) ≥ 0.5
```

A row is then split into separate lines wherever the gap between two words is wider than
`gutter_min_width_pt` (see 2.3), so the left and right columns of a two-column page do not merge
into one line.

*Justification:* Words on one line share most of their height, even when their sizes differ: a
small glyph such as a bullet sits entirely inside the line (ratio 1.0). Consecutive lines barely
overlap, because line spacing is normally at least the font size (ratio near 0, at most about 0.2
with very tight spacing). 0.5 sits safely between the two.

Within a line, words are ordered left to right; words starting at the same x are ordered
narrower first.

*Found on a real resume:* An earlier version grouped words whose top edges were within 3 points.
On one resume the visible bullets were drawn shapes, and an invisible 0.75 pt text bullet sat over
the first letter of each item, on the text's baseline and 6.7 points below the line's top.
Top-edge grouping moved that bullet to the end of the line ("Managed •"); overlap grouping and the
narrower-first rule put it back in front.

The three readings of a PDF page are:

- **Content-stream order:** `pypdf`'s `extract_text()`.
- **Position order:** `pdfplumber`'s `extract_text()`.
- **Column-aware order:** our lines. Without a gutter (2.3), rows are read top to bottom. With a
  gutter, each line is on the left (it ends before the right column starts), on the right (it
  starts after the left column ends) or spans both columns. Spanning lines split the page into
  blocks; in a block, the left column is read before the right one when both sides hold at least
  two rows, otherwise the block is read row by row (this keeps a contact row with items on both
  sides together). Lines are kept in this order, so a section heading only collects the lines of
  its own column.

**DOCX.** `python-docx` gives paragraphs in body order, tables, and each section's header and
footer. Text boxes are read from the raw XML (`w:txbxContent`), because `python-docx` does not
expose them; Word stores each box twice (DrawingML and a VML fallback) and only one copy is read.
Font size and boldness come from the runs, falling back to the paragraph style. Hyperlink targets
are collected for 2.7 in both formats.

### 2.1 Text layer (`min_chars_per_page = 50`, `scan_image_coverage = 0.5`, `outline_min_curves = 200`)

A PDF page has **no text layer** when it holds fewer than 50 non-whitespace characters **and** its
content is a picture: an image covering at least half of the page, or at least 200 vector curves
(text converted to outlines) → **critical** (it breaks every strategy; only an ATS that runs OCR
would read it [4]). A DOCX with fewer than 50 characters in all is treated the same way.

*Justification:* A typical resume page contains 1,500–3,000 characters (our observation). Below 50
means only fragments such as a page number could be extracted. The picture condition was added
after testing: a two-page resume whose second page held only the Languages section (39
characters) was reported as a scan. A scanned page is one image over the whole page (coverage
1.0 in the test set). Outlined text draws at least one curve per letter, so a page of it has well
over a thousand curves, while decorations in the test set drew at most 18; 200 lies between the
two, but no outlined resume has been measured yet.

### 2.2 Garbled characters (`garbled_warn = 0.02`, `garbled_critical = 0.10`)

```
g = garbled_characters / total_characters
```

Counted as garbled, in the column-aware reading: `(cid:NN)` patterns (fonts without a character
map), `U+FFFD` (�) and the Unicode private use area `U+E000–U+F8FF` (icon fonts).

- `g > 0.02` → **warning**, `g > 0.10` → **critical**

*Justification:* Up to 2% can come from icons and bullet glyphs without hurting readability.
Above 10%, words become unreadable.

### 2.3 Multi-column layout (`gutter_min_width_pt = 8`, `gutter_min_height = 0.5`, `gutter_x_range = [0.2, 0.8]`)

A **gutter** is an empty vertical channel between two columns:

1. Between 20% and 80% of the page width, the page is scanned in 1-point slices. A channel is a
   run of slices, at least 8 points wide, that share one vertical stretch of at least 50% of the
   page's text height which no line crosses.
2. The channel separates two columns when, within that stretch, each side holds a column of
   **left-aligned text**: at least two rows that start at the same x and end at different x.
3. The widest such channel is the gutter.

On a page with a gutter, a reading **scrambles the columns** when its word order differs from the
column-aware reading (as in 2.4), or when it joins text from the left and the right column of the
same row side by side on one output line. The finding is a **warning** naming the strategies that
scramble the columns, or **info** when every strategy keeps them apart.

*Justification:* Measured gutters in the test set are 14 to 53 points wide (a Word table used as a
layout has the narrowest), while the gap between words is 3–5 points; 8 points separates the two.
Requiring the empty stretch rather than a share of all lines lets a full-width header (name,
contact, summary) sit above the columns. The left-alignment condition tells a column from a stack
of right-aligned dates ("Jan 2021 – Present"), which end at the same x and start at different x.
Columns are a problem only for readers that interleave them; Tika documents that position sorting
"can interleave columns" [4]. Textkernel estimates that at least 15% of CVs use columns and
describes its earlier rule-based detection of visual gaps, which this method resembles [6].

*Found while testing:* the first version required that at most 5% of all lines cross the channel
and that each side span 50% of the text height. It missed Word's two-column and table layouts
(the header crossed the channel; the right column was short) and, once relaxed, took right-aligned
dates for a column. With a narrow right column (one skill per row), position order glued each
skill to the end of an experience line yet kept 85% of the word order; the side-by-side test
catches this case.

### 2.4 Reading order and lost words (`agreement_order_max = 0.85`)

For each page, the word sequence of each simple reading (content-stream, position) is compared
with the column-aware reading:

```
order_similarity = 1 − Indel distance(A, B) / (|A| + |B|)
```

This is the share of words that appear in the same relative order (2 × longest common
subsequence / total length), computed with `rapidfuzz`. If `order_similarity < 0.85` on a page
without a gutter → **warning**: the reader puts the text in a different order than the page shows.

Separately, every word of the column-aware reading that is missing from a simple reading is
listed → **warning**: a recruiter searching for that word does not find the resume in such ATSs.
Words are compared after folding (see 2.6), so only real splits count.

*Justification:* On the two real resumes measured so far, readings that keep the page's order
scored 0.95–1.00, while readings that scrambled a two-column page scored 0.61–0.71 (our
observation, see Calibration). 0.85 separates the two with a margin on both sides. *Found on a
real resume:* the content-stream reading split "İstanbul" into "İ stanbul" and "TÜBİTAK" into
"TÜB İ TAK", because the letter İ came from a separate font subset.

### 2.5 Content outside the body (DOCX)

- Email or phone found **only** in a header or footer → **warning** for "body paragraphs only".
- Any text inside text boxes → **warning** for "body paragraphs only".

PDF has no separate header: the top of the page is extracted like any other text, so no finding
is made for PDF.

*Justification:* Headers, footers and text boxes are separate parts of a DOCX file, and readers
that take only the body paragraphs never see them (see the DOCX strategies in section 1).

### 2.6 Section headings (`heading_max_words = 4`, `heading_size_ratio = 1.15`, `heading_match_min = 85`)

A line is a **heading candidate** if it has at most 4 words, does not start with a bullet, and at
least one of: font size ≥ 1.15 × the median word size, bold, all capitals, or a Word heading style.

Candidates are compared with a dictionary of standard English and Turkish headings
(`resume_xray/data/headings.toml`) using `rapidfuzz.fuzz.ratio ≥ 85`, after **folding**: lowercase,
`İ`/`I`/`ı` → `i`, other Turkish letters to ASCII (`ş` → `s`, ...), punctuation removed. Folding lets
"EXPERIENCE", "Experience", "DENEYİM" and "Deneyim" match regardless of the language they were
lowercased in.

- A core section (experience, education, skills) is not recognized → **warning**.
- A candidate that is not in the dictionary but has the same style (size, boldness, capitals) as
  the recognized headings and comes after the first one → **warning**, with the closest standard
  heading suggested. Requiring the same style keeps the name and bold job titles from being taken
  for headings.
- A recognized heading that is not on a line of its own in a reading → **warning** naming those
  strategies: a parser looking for heading lines does not see it.

*Justification:* Parsers classify sections using heading dictionaries. A threshold of 85 catches
spelling variants ("Experiences", "Language") while leaving unrelated words out. A missing
section is a warning, not critical: the rest of the resume is still read.

### 2.7 Contact details and dates (`phone_min_digits = 10`, `phone_max_digits = 15`)

Regular expressions look for an email address, a phone number (a run of digits with spaces,
dots, dashes, parentheses or a leading `+`, holding 10 to 15 digits) and a LinkedIn URL.

- No reading contains an email address → **critical**.
- A LinkedIn URL exists only as a hyperlink target, not as text → **info**: text extraction
  returns the visible text, not link targets.
- A date written with a season or quarter ("Summer 2021", "Yaz 2021", "Q3 2021") → **warning**: it
  cannot be turned into a month.

*Justification:* 10 digits is the length of a national number in Turkey and North America; 15 is
the maximum length of an international number under ITU-T E.164 [9].

### 2.8 Misplaced bullets (`bullet_size_ratio = 0.5`)

For each simple reading, round bullets (`•`, `●`, `▪`, `■`, `◦`, `►`) that are alone on a line or
not at the start of a line are counted. If any reading has misplaced bullets → **warning** naming
those readings and how many bullets each misplaced. If the bullets in the column-aware reading are
smaller than 0.5 × the median size of the rest of their line, the finding explains that the
bullets are tiny glyphs drawn apart from the text.

*Justification:* Some resume builders (typically HTML-to-PDF exports) draw the visible bullet as a
shape and add a tiny text bullet for copy and paste. Position-order readers then put the bullet on
its own line after the first line of the item, so the next item appears to start in the middle of
the previous one. Content-stream readers read the same file correctly, so the outcome depends on
which reader an ATS uses. Normally styled bullets are 50–100% of the text size (our observation);
the case that motivated this check was 7.5% (0.75 pt next to 10 pt text).

---

## 3. Job match

Recruiters find candidates in an ATS with keyword and Boolean searches over resume text. Greenhouse,
for example, documents a full-text "search resumes for keywords" feature [10] and Boolean queries in
which matching "plurals or different word forms" needs an explicit `*` wildcard [11]; neither page
mentions synonym expansion. Job matching therefore asks: **would a search with the job's own words
find this resume?** Some ATSs may stem words or expand synonyms; since that is not documented for
the systems we checked, such matches get partial credit and an explanation instead of full credit.

### 3.1 Normalization

1. **Language** of each text (resume, job description) is detected by counting common English and
   Turkish function words.
2. **Apostrophe suffixes** are dropped: "Python'da" → "Python" (Turkish attaches suffixes to proper
   nouns with an apostrophe).
3. **Lowercasing:** `İ → i` in every language; `I → ı` only in Turkish text. Python's plain
   `str.lower()` gets both wrong for Turkish.
4. **Tokens** keep `+`, `#`, `.` and `&` inside them, so `C++`, `C#`, `.NET`, `Node.js` and `R&D`
   stay whole (and `R&D` is not mistaken for the R language).
5. Each token gets two keys, both folded to ASCII (`ş → s`, `ı → i`, ...):
   - **surface:** the word as written, lowercased;
   - **stem:** its Snowball stem in the text's language (English or Turkish): "managed" and
     "management" share the stem "manag".

### 3.2 Terms of the job description

**Sections.** A short line (at most `heading_max_words` words) that matches a known heading in
`resume_xray/data/job_sections.toml` (`rapidfuzz.fuzz.ratio ≥ heading_match_min`) starts a section:

| Section kind | Examples | Effect |
|---|---|---|
| Required | Requirements, Qualifications, Responsibilities, Aranan Nitelikler, Sorumluluklar | Terms are required |
| Preferred | Nice to have, Preferred, Bonus, Tercih Sebepleri | Terms are preferred |
| Ignored | About Us, Benefits, What We Offer, Hakkımızda, Yan Haklar | Lines are skipped |
| (none yet) | Text before the first heading | Treated as required |

A line containing a preference cue ("is a plus", "preferred", "tercih sebebidir", ...) makes its
terms preferred in any section.

**Job title** (`title_max_words = 8`): the first line of the job description, if it comes before any
section heading and has at most 8 words. Otherwise the job description has no title line (many
start with "About the Role" and a sentence), and the user can give it with `--title`.

*Justification:* Job titles are short ("Senior Backend Developer", "Kıdemli Proje Yöneticisi"); a
longer first line is a sentence, not a title.

**Terms.**

- **Skill dictionary** (`resume_xray/data/skills.toml`): each skill lists every wording that means
  it (`Kubernetes`, `K8s`). The job is searched by **stem**, longest wordings first, without
  overlaps, so "React Native" is not also counted as "React". The wording the job actually used is
  kept. Wordings of one or two characters (`R`, `C`, `Go`, `UI`) must also match capitals.
- **Technical-looking words** not in the dictionary: words with a letter and a digit, `+` or `#`,
  CamelCase (`PostgreSQL`, `ISO27001`, `iOS`), or acronyms of two or more capital letters
  (`ARPU`, `LTV`, `AI`).

**User terms.** No dictionary covers every field, so the user has the last word on which terms
count:

- **Add** (`--add`): each added term is **required**. If it is a wording in the skill dictionary,
  it brings that skill's synonyms; otherwise it is matched as written. Its `f_t` is the number of
  times it appears in the job description, at least 1.
- **Remove** (`--remove`): terms whose name or job wording equals a removed term are dropped.
- **Only my terms** (`--skills`): no job description; coverage is computed over the given terms.

*Found on a real job description:* a product manager posting yielded 9 terms; "product strategy",
"monetization", "experimentation" and "stakeholders" were not in the dictionary.

**One-word stems** (`word_form_max_extra = 2`): a one-word wording matches another form of the
word only if their lengths differ by at most 2 letters. This applies to the job and the resume
alike.

*Justification:* Plural and short inflected forms differ by one or two letters ("roadmap" /
"roadmaps", "Liderlik" / "Liderliği"), but stemming also merges unrelated words: Snowball reduces
both "Excel" and "Excellent" to "excel". *Found on a real job description:* "Excellent
communication skills" was taken as a requirement for Excel.

### 3.3 Term weight (`required_weight = 1.0`, `preferred_weight = 0.5`)

```
w_t = r_t × (1 + ln(1 + f_t))
```

**`r_t` — requirement factor:** `1.0` for required terms, `0.5` for preferred ones. A term that is
both required and preferred somewhere counts as required.

*Justification:* We trust the job author's own required/preferred split. 0.5 is the simplest form
of the assumption "a preferred term is half as important as a required one". Text outside a known
section is treated as required so that gaps are not missed; sections about the company and its
benefits are skipped because their tools (e.g. "we use Slack") are not requirements.

**`f_t` — number of times the term appears in the counted lines.**

*Justification:* The more often a term appears, the more important it is, but the effect is
**saturated** with a logarithm: a term appearing once gets ×1.69 weight, one appearing 5 times gets
×2.79 (not 5×). This is the same idea as term-frequency saturation in BM25, and it keeps a single
word repeated 10 times from overwhelming all other terms.

### 3.4 Match level (`word_form_match = 0.5`, `synonym_match = 0.5`)

The resume is searched in its column-aware (PDF) or all-parts (DOCX) reading:

| Case | `m_t` | Justification |
|---|---|---|
| **Exact:** one of the job's wordings, same surface key | 1.0 | A keyword search with the job's word finds it |
| **Word form:** same stem, different form ("roadmaps" / "roadmap") | 0.5 | Found only with a wildcard search [11]; the user is told which form the job uses |
| **Synonym:** another wording of the same skill ("Kubernetes" / "K8s") | 0.5 | Same meaning, but synonym expansion is not documented [10, 11]; the user is told to add the job's wording |
| Absent | 0 | — |

### 3.5 Coverage

```
Coverage = Σ (w_t × m_t) / Σ w_t
```

Computed and shown **separately** for required and preferred terms. No overall score is formed.

For every term found, the report also shows:

- **where** it appears, by the resume's own section headings (an experience bullet vs. only the
  skills list). This does **not** affect coverage: search finds it in either place; an in-context
  mention matters to the human reader.
- **in which readings it is lost**, if any: a term found in the column-aware reading but not in,
  say, the content-stream reading (because a letter was split off, see 2.4) is not found by an ATS
  that reads that way.

### 3.6 Separate checks (not part of coverage)

| Check | Method | Why separate |
|---|---|---|
| Job title | Found when one resume line contains the title as an exact phrase (same keys as exact terms), like a quoted phrase search [11]. *Found while testing:* a fuzzy comparison took "Project Manager" for "Product Manager" (87% similar); a recruiter's search would not | The field recruiters search most |
| Years of experience | The largest "N+ years" / "N yıl" in the counted lines of the job. In the resume, date ranges in the experience section (`MM/YYYY`, `Jan 2021`, `Oca 2021`, `2021`, "Present" / "Günümüz" = today) are merged so that overlapping periods count once. A year without a month starts in January and ends in December | A knockout criterion, must not be mixed with coverage |
| Degree | Levels Bachelor < Master < PhD, recognized in English and Turkish ("lisans", "yüksek lisans", "doktora", "BSc", "MSc"). The job's requirement is the **lowest** level it mentions ("Bachelor's or Master's" → Bachelor); the resume's is the **highest** level in its education section | A knockout criterion |

---

## 4. Why no TF-IDF, embeddings or LLM?

| Method | Why it is not used |
|---|---|
| TF-IDF + cosine | IDF needs many documents to be meaningful; we have 2. The result cannot answer "why?" |
| Embeddings (sentence-transformers etc.) | A black box; documented name/gender bias [7]; needs a ~1 GB model download. ATS search is word-based, not semantic |
| LLM | Not deterministic (different results for the same resume); sending the resume out is a privacy risk |

Embeddings may be added later as an **off-by-default** option that only produces "this term may
also be related" suggestions; they never enter the coverage computation.

---

## 5. Calibration

Thresholds are validated with labeled test resumes in `tests/fixtures/`. Target set (~30
documents):

- single-column, two-column and table-based PDFs
- Canva / design-tool exports, documents with icon fonts
- scanned (image) PDFs
- DOCX files with text boxes and contact info in the header
- English and Turkish resumes

The expected findings for each document are labeled by hand. Whenever a threshold changes, the
test set is re-run and the result is recorded here.

| Version | Change | Test result |
|---|---|---|
| 0.1 | Starting values | — (no test set yet) |
| 0.1 | `agreement_order_max` 0.7 → 0.85; reading order compared with the column-aware reading | Two real resumes (one single-column, one two-column): order-keeping readings 0.945–1.000, scrambled readings 0.608–0.707 |
| 0.1 | Synthetic test set of 23 resumes (`tests/fixtures/synthetic/`, made with Chrome and Word). Words built from characters (`word_gap_pt` 3); scans need a picture (`scan_image_coverage` 0.5, `outline_min_curves` 200); gutter redefined as an empty channel beside left-aligned text, `gutter_min_width_pt` 15 → 8, `gutter_max_coverage` removed | All 23 agree with their labels. Gutters found in all 6 two-column PDFs (14–53 pt) and in none of the single-column ones; order of readings that keep the page's order 0.97–1.00 |
| 0.1 | **First blind hold-out, before any change:** 22 real and template resumes (by the labels: Canva 11, Overleaf 5, Google Docs 4, job sites 2; 11 English, 11 Turkish) labeled by the maintainer without seeing resume-xray's results | 164 of 204 expectations agree (80%); 4 of 22 resumes agree fully. Disagreements: 13 from the labeling tool (it expected sections and an email in image-only PDFs), 4 from a question that listed only five standard headings, the rest from heading matching (headings with an extra word such as "Relevant Work Experience"), "Eğitimler" mapped to courses, and words joined in LaTeX PDFs. This set is no longer blind after the fixes below |

---

## References

Checked on 2026-10-14.

1. Oracle, *Taleo Enterprise: Candidate Prescreening*.
   https://docs.oracle.com/en/cloud/saas/taleo-enterprise/20b/otrec/candidate-prescreening.html
2. Lenz, *Fact check: "75% of resumes are rejected by ATS"*.
   https://lenz.io/c/ats-applicant-tracking-system-75-percent-rejection-rate-bc6fd7d4
   (secondary source; the original 2012 Preptel material is no longer online)
3. Apache PDFBox, *PDFTextStripper* Javadoc, `setSortByPosition`.
   https://pdfbox.apache.org/docs/2.0.13/javadocs/org/apache/pdfbox/text/PDFTextStripper.html
4. Apache Tika, *PDFParser Configuration* (4.0.x).
   https://tika.apache.org/docs/4.0.x/configuration/parsers/pdf-parser.html
5. Poppler, *pdftotext(1)* manual page.
   https://manpages.debian.org/trixie/poppler-utils/pdftotext.1.en.html
6. Textkernel, *Improving extraction from column resumes*.
   https://textkernel.com/learn-support/blog/improving-extraction-from-column-resumes
7. Wilson, K. and Caliskan, A. (2024). *Gender, Race, and Intersectional Bias in Resume Screening
   via Language Model Retrieval.* AAAI/ACM Conference on AI, Ethics, and Society.
   https://arxiv.org/abs/2407.20371
8. mammoth (Python), README.
   https://github.com/mwilliamson/python-mammoth
9. ITU-T, *Recommendation E.164: The international public telecommunication numbering plan*.
   https://www.itu.int/rec/T-REC-E.164 (the 15-digit limit is summarized at
   https://en.wikipedia.org/wiki/E.164; the recommendation text itself is not freely shown)
10. Greenhouse, *Search resumes for keywords*.
    https://support.greenhouse.io/hc/en-us/articles/115004600186-Search-resumes-for-keywords
11. Greenhouse, *Search candidates using Boolean queries*.
    https://support.greenhouse.io/hc/en-us/articles/202360199-Search-candidates-using-Boolean-queries
