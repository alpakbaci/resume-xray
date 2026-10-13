# resume-xray

See how an applicant tracking system (ATS) reads your resume, section by section.

> **Status:** under development. The command-line tool works from source; the web interface is
> next. See [ROADMAP.md](ROADMAP.md).

- **Local.** Runs on your computer. Your resume never leaves your machine: no uploads, no
  accounts, no telemetry, works offline.
- **Open.** Every check, formula, threshold and weight is documented in
  [ALGORITHM.md](ALGORITHM.md), with the reason it was chosen.
- **No LLM.** Results are deterministic: the same resume always gives the same report.

## What it tells you

Upload a PDF or DOCX resume and, optionally, paste a job description:

1. **Can an ATS parse it?** `OK`, `Risky` or `Unreadable`, with each problem explained: scanned
   pages, broken fonts, multi-column layouts, contact details in the header, unrecognized
   section headings, unparseable dates. You also see the raw text an ATS would extract.
2. **Will you show up in a recruiter's search?** Which required and preferred terms from the job
   description are in your resume, which are missing, and which are only present as synonyms.

## What it does not tell you

It does not predict whether you will be hired or reproduce any vendor's score. No ATS publishes
one. And the often-quoted "75% of resumes are rejected by ATS" is a myth: it comes from a 2012
sales pitch with no published methodology.

## Usage (from source)

```bash
git clone <this repository> && cd resume-xray
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

```bash
resume-xray                                   # opens the web interface in your browser
resume-xray my_resume.pdf                     # can an ATS parse it?
resume-xray my_resume.pdf --job job.txt       # ... and which job terms are missing
resume-xray my_resume.pdf --job job.txt --add "Scrum Master, SAP FI" --remove "English"
resume-xray my_resume.pdf --skills "Python, Docker, risk management"   # your own term list
resume-xray my_resume.pdf --raw               # the text each ATS reading strategy extracts
resume-xray my_resume.pdf --json              # machine-readable report
```

A `pip install resume-xray` release with a local web interface will follow.

## License

[MIT](LICENSE). Third-party components and their licenses are listed in
[THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).
