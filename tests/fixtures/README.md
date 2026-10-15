# Test resumes

## Synthetic set (`synthetic/`)

23 resumes of invented people, each built to show one layout or problem: single and two-column,
sidebar, tables, letter-spaced headings, tiny text bullets, text boxes, contact details in the
header, a scanned page, unusual headings and dates, Turkish text. They are made with real tools so
they carry real-world quirks:

- PDFs from HTML are printed by Google Chrome, like the "Download PDF" button of many web resume
  builders.
- DOCX files are built with python-docx; their PDFs are exported by Microsoft Word.
- The scanned PDF is a page image.

Regenerate them on macOS with Chrome and Word installed:

```bash
python tools/make_fixtures.py
```

## Labels

Every resume has a label next to it, named after the file plus `.toml` (`cv.pdf.toml`). All keys
are optional:

```toml
verdict = "Risky"                        # OK, Risky or Unreadable
must_find = ["columns_scramble"]         # finding codes that must be reported
must_not_find = ["no_email"]             # finding codes that must not be reported
sections = ["experience", "education"]   # sections that must be recognized
note = "Why the label says this."

[affects]                                # a finding must name at least these readings
columns_scramble = ["position"]

[not_affects]                            # a finding must not name these readings
columns_scramble = ["columns"]
```

A label states what is true of the document, decided by looking at it and at the text each reader
extracts (`resume-xray FILE --raw`), never by copying what resume-xray reports. The `note` says how
it was decided.

## Private resumes

Real resumes (Canva, LinkedIn, job sites, your own) are the most valuable test cases, but they
cannot be committed: they hold personal data and their templates are often copyrighted. Keep them
in `~/resume-xray-private/`, each with a label. A plain `pytest` never reads them, so it cannot
reveal results while labeling is in progress; to include them, name the folder:
`RESUME_XRAY_PRIVATE=~/resume-xray-private pytest`.

They are a **hold-out set**, labeled blind:

1. Label first: `python tools/label.py` shows each resume next to questions anyone can answer by
   looking at it (is the text selectable, how many columns, which headings, is the email written
   out...). It never runs resume-xray, so the label cannot copy the tool's answer.
2. Never tune a threshold on these files. They only measure how often the tool agrees with a person.
3. When the tool and a label disagree, decide who is right from the page image and the raw readings
   (`resume-xray FILE --raw`). A tool error is fixed and recorded in the calibration table as found on
   a real resume; a label error is corrected with a note saying why.

With n resumes and no disagreement, the error rate is below about 3/n at 95% confidence (the rule
of three): 20 resumes support "below 15%", 30 support "below 10%".

## Calibration

```bash
python tools/calibrate.py                         # synthetic set
python tools/calibrate.py ~/resume-xray-private   # plus private resumes
```

prints, for every resume, the findings and the measurements behind the thresholds (order
similarity of each reading, gutter width, bullet size ratio) and where a report disagrees with its
label. Results go into the calibration table of `ALGORITHM.md`.
