# resume-xray

See how an applicant tracking system (ATS) reads your resume, section by section.

> **Status:** under development, not usable yet. See [ROADMAP.md](ROADMAP.md).

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

## Installation

Coming with the first release. It will be:

```bash
pip install resume-xray
resume-xray
```

## License

[MIT](LICENSE). Third-party components and their licenses are listed in
[THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).
