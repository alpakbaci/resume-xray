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
   years of experience (unrelated to the resume text).

resume-xray measures **points 1 and 2**. It does not measure:

- Whether you will be hired, or "the score an ATS would give you". No ATS vendor publishes such a
  score; a tool claiming to reproduce one is guessing.
- The claim that "75% of resumes are rejected by ATS" is a **myth**. It traces back to a 2012 sales
  pitch by Preptel, a resume-optimization company that shut down in 2013, and no methodology was
  ever published.

### No single score

Results are not given as a single "73% match" number. Adding unrelated findings (a font problem,
a missing skill, a column layout) with arbitrary weights cannot be justified and hides critical
failures inside an average. Instead, two separate questions are answered:

| Question | Answer format | Rule |
|---|---|---|
| Can my document be parsed? | `OK` / `Risky` / `Unreadable` | The worst finding wins |
| Will I be found for this job? | Separate coverage for required and preferred terms | Weighted coverage (section 3) |

---

## 2. Parseability

Each check produces a **severity**: `critical`, `warning` or `info`. There are no weights, only
thresholds.

- Any `critical` finding → **Unreadable**
- No `critical`, at least one `warning` → **Risky**
- Otherwise → **OK**

### 2.0 Reading the document (`line_tolerance_pt = 3`)

Both formats are converted into one shared representation: lines of text with their page, font
size, boldness and region (body, header, footer, table, text box). PDF lines also carry their
position in points. All checks below work only on this representation.

**PDF.** `pdfplumber` gives every word with its coordinates, font name and size. Words whose top
edges are within 3 points of each other form one visual row. A row is then split into separate
lines wherever the gap between two words is wider than `gutter_min_width_pt` (see 2.3), so the
left and right columns of a two-column page do not merge into one line. A word counts as bold when
its font name contains Bold, Black, Heavy, Semibold or Demi. The page's raw text, as a simple ATS
would extract it, comes from `pdfplumber`; `pypdf` reads the same page a second time for 2.4.

*Justification:* Words on the same row differ in their top edge by at most 1–2 points (for example
a bold label next to regular text), while the next row is at least one line height away (about
8 points or more for body text). 3 points sits safely between the two.

**DOCX.** `python-docx` gives paragraphs in body order, tables, and each section's header and
footer. Text boxes are read from the raw XML (`w:txbxContent`), because `python-docx` does not
expose them. Font size and boldness come from the runs, falling back to the paragraph style. The
number of columns declared in the section settings (`w:cols`) is kept for 2.3.

### 2.1 Text layer (`min_chars_per_page = 50`)

The number of characters extracted from each page, `n_c`, is computed. If `n_c < 50`, the page is
a scanned image → **critical**.

*Justification:* A typical resume page contains 1,500–3,000 characters. Below 50 means only
fragments such as a page number could be extracted.

### 2.2 Garbled character ratio (`garbled_warn = 0.02`, `garbled_critical = 0.10`)

```
g = garbled_characters / total_characters
```

Counted as garbled: `(cid:NN)` patterns (fonts without a ToUnicode map), `U+FFFD` (�) and the
Unicode private use area `U+E000–U+F8FF` (icon fonts).

- `g > 0.02` → **warning**, `g > 0.10` → **critical**

*Justification:* Up to 2% can come from icons and bullet glyphs without hurting readability.
Above 10%, words become unreadable.

### 2.3 Multi-column detection (`gutter_min_width_pt = 15`, `gutter_max_coverage = 0.05`, `gutter_min_height = 0.5`, `gutter_x_range = [0.2, 0.8]`)

The page width is split into 1-point slices. For each slice:

```
coverage(x) = lines with a word box crossing the slice / total lines
```

If, between 20% and 80% of the page width, there is a continuous channel at least 15 points wide
with `coverage(x) ≤ 0.05`, **and** that channel runs for at least 50% of the text height, the page
is considered **multi-column** → **warning**.

*Justification:* The gap between columns is usually wider than 15 points, while the gap between
words is 3–5 points. The 50% height condition avoids flagging single-column pages that only have
side-by-side items in the header. The result is **not critical**, because modern commercial
parsers (e.g. Textkernel) usually handle columns; older and in-house systems may not. This method
resembles Textkernel's early rule-based column detection.

### 2.4 Reader agreement (`agreement_bag_min = 0.9`, `agreement_order_max = 0.7`)

The PDF is read with both `pdfplumber` and `pypdf`, and the word sequences are compared:

```
bag_similarity   = |A ∩ B| / |A ∪ B|              (Jaccard, word sets)
order_similarity = SequenceMatcher(A, B).ratio()  (word sequences)
```

If `bag_similarity > 0.9` **and** `order_similarity < 0.7` → **warning**: "reading order is
ambiguous".

*Justification:* Different ATSs use different PDF readers. If two readers extract the same words
in a different order, the document is likely to be read scrambled by some systems. This is an
independent signal supporting 2.3.

### 2.5 Contact info in header/footer (`header_footer_band = 0.08`)

- PDF: the top and bottom 8% band of the page height.
- DOCX: the document's header/footer parts (stored separately from the body in the file).

If the email or phone number is found **only** in these areas → **warning**.

*Justification:* Some parsers and libraries (e.g. mammoth, naive python-docx usage) skip headers
and footers. The fix is easy and the risk is real.

### 2.6 Section detection (`heading_max_words = 4`, `heading_size_ratio = 1.15`, `heading_match_min = 85`)

A line is a **heading candidate** if:

- it has at most 4 words, **and**
- one of: font size ≥ body median × 1.15, bold, or all caps.

The candidate is compared against an English/Turkish heading dictionary
(`rapidfuzz.fuzz.ratio ≥ 85`).

- One of the core sections (experience, education, skills) is not found → **critical**
- A heading candidate with no match in the dictionary → **warning**, with the closest standard
  heading suggested (e.g. "My Projects" → "Projects")

*Justification:* Parsers classify sections using heading dictionaries. A threshold of 85 catches
spelling variants ("Experiences", "Is Deneyimi") while leaving unrelated words out.

### 2.7 Field extraction

Regular expressions look for: email, phone (Turkish and international formats), LinkedIn URL and
date ranges (`MM/YYYY`, `Jan 2021`, `Oca 2021`, `2019–2021`, "Present" / "Günümüz").

- No email at all → **critical**
- The date of an experience entry cannot be parsed (e.g. "Summer 2021") → **warning**

---

## 3. Job match

### 3.1 Normalization (same for resume and job description)

1. Unicode NFKC normalization.
2. **Turkish-aware lowercasing:** `I → ı`, `İ → i`. Python's `str.lower()` gives wrong results for
   Turkish; this is the most common matching bug on Turkish text.
3. `+`, `#` and `.` are kept; otherwise `C++`, `C#`, `.NET` are lost.
4. Snowball stemming (language detected by counting stopwords): "Python'da" → "python".

### 3.2 Term extraction from the job description

- **Skill dictionary:** matches of 1–3 words. The dictionary contains synonyms
  (`k8s → kubernetes`, `js → javascript`). It starts as a hand-curated technology list; ESCO
  (28 languages including Turkish) will be added later.
- **Technical-looking words:** words containing digits, `+`, `#`, or written in CamelCase are taken
  as candidate terms.

### 3.3 Term weight (`required_weight = 1.0`, `preferred_weight = 0.5`)

```
w_t = r_t × (1 + ln(1 + f_t))
```

**`r_t` — requirement factor**

| Job description section the term appears in | `r_t` |
|---|---|
| "Requirements", "Must have", "Aranan nitelikler" | 1.0 |
| "Nice to have", "Preferred", "Tercih sebebi" | 0.5 |
| Unclear | 1.0 |

*Justification:* We trust the job author's own required/preferred split. 0.5 is the simplest form
of the assumption "a preferred term is half as important as a required one". Unclear sections are
treated as required so that gaps are not missed.

**`f_t` — number of times the term appears in the job description**

*Justification:* The more often a term appears, the more important it is, but the effect is
**saturated** with a logarithm: a term appearing once gets ×1.69 weight, one appearing 5 times gets
×2.79 (not 5×). This is the same idea as term-frequency saturation in BM25, and it keeps a single
word repeated 10 times from overwhelming all other terms.

### 3.4 Match level (`synonym_match = 0.5`)

| Case | `m_t` | Justification |
|---|---|---|
| Exact match after normalization | 1.0 | A recruiter searching with the job's wording finds it |
| Only a synonym is present (job says "Kubernetes", resume says "k8s") | 0.5 | Same meaning, but ATS search is word-based and may miss it. The user is told to also add the job's wording |
| Absent | 0 | — |

### 3.5 Coverage

```
Coverage = Σ (w_t × m_t) / Σ w_t
```

Computed and shown **separately** for required and preferred terms.

Where the term appears in the resume (an experience bullet vs. only the skills list) is also
reported, but it **does not affect coverage**. ATS search finds it in either place; the fact that
an in-context mention is more valuable is advice about the human reader.

### 3.6 Separate checks (not part of coverage)

| Check | Method | Why separate |
|---|---|---|
| Job title | Job title vs. titles in the resume: `rapidfuzz.fuzz.token_set_ratio ≥ 85` | The field recruiters search most |
| Years of experience | "5+ years" pattern in the job; resume date ranges merged (overlapping periods counted once) | A knockout criterion, must not be mixed with coverage |
| Degree | "bachelor/lisans" etc. patterns searched in the education section | A knockout criterion |

---

## 4. Why no TF-IDF, embeddings or LLM?

| Method | Why it is not used |
|---|---|
| TF-IDF + cosine | IDF needs many documents to be meaningful; we have 2. The result cannot answer "why?" |
| Embeddings (sentence-transformers etc.) | A black box; documented name/gender bias (Wilson & Caliskan, AIES 2024); needs a ~1 GB model download. ATS search is word-based, not semantic |
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
