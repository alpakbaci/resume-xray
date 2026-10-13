# Third-party licenses

ats-checker is MIT licensed. It uses only permissively licensed components (MIT, BSD, Apache-2.0,
PSF; fonts under SIL OFL). Their license texts ship inside each installed package.

Versions below were checked from installed package metadata on 2026-10-14.

## Direct dependencies

| Package | Version | License | Used for | Source |
|---|---|---|---|---|
| pdfplumber | 0.11.10 | MIT | PDF text, word coordinates, fonts | https://github.com/jsvine/pdfplumber |
| pypdf | 6.20.1 | BSD-3-Clause | Second PDF reader (agreement check) | https://github.com/py-pdf/pypdf |
| python-docx | 1.2.0 | MIT | DOCX reading | https://github.com/python-openxml/python-docx |
| snowballstemmer | 3.1.1 | BSD-3-Clause | Stemming (English, Turkish) | https://github.com/snowballstem/snowball |
| RapidFuzz | 3.14.6 | MIT | Fuzzy matching of headings and titles | https://github.com/rapidfuzz/RapidFuzz |
| FastAPI | 0.143.0 | MIT | Local web interface | https://github.com/fastapi/fastapi |
| Uvicorn | 0.54.0 | BSD-3-Clause | Local web server | https://github.com/encode/uvicorn |
| python-multipart | 0.0.32 | Apache-2.0 | File upload handling | https://github.com/Kludex/python-multipart |

## Transitive dependencies

| Package | License | Pulled in by | Source |
|---|---|---|---|
| pdfminer.six | MIT | pdfplumber | https://github.com/pdfminer/pdfminer.six |
| pypdfium2 (bundles PDFium) | BSD-3-Clause, Apache-2.0 | pdfplumber | https://github.com/pypdfium2-team/pypdfium2 |
| Pillow | MIT-CMU | pdfplumber | https://github.com/python-pillow/Pillow |
| charset-normalizer | MIT | pdfminer.six | https://github.com/jawah/charset_normalizer |
| cryptography | Apache-2.0 OR BSD-3-Clause | pdfminer.six | https://github.com/pyca/cryptography |
| cffi | MIT-0 | cryptography | https://github.com/python-cffi/cffi |
| pycparser | BSD-3-Clause | cffi | https://github.com/eliben/pycparser |
| lxml | BSD-3-Clause | python-docx | https://lxml.de/ |
| Starlette | BSD-3-Clause | FastAPI | https://github.com/Kludex/starlette |
| Pydantic, pydantic-core | MIT | FastAPI | https://github.com/pydantic/pydantic |
| annotated-types | MIT | Pydantic | https://github.com/annotated-types/annotated-types |
| annotated-doc | MIT | FastAPI | https://github.com/fastapi/annotated-doc |
| typing-inspection | MIT | Pydantic | https://github.com/pydantic/typing-inspection |
| typing_extensions | PSF-2.0 | several | https://github.com/python/typing_extensions |
| opentelemetry-api | Apache-2.0 | FastAPI | https://github.com/open-telemetry/opentelemetry-python |
| AnyIO | MIT | Starlette | https://github.com/agronholm/anyio |
| idna | BSD-3-Clause | AnyIO | https://github.com/kjd/idna |
| Click | BSD-3-Clause | Uvicorn | https://github.com/pallets/click |
| h11 | MIT | Uvicorn | https://github.com/python-hyper/h11 |

`opentelemetry-api` is only the tracing interface. Without an OpenTelemetry SDK and exporter
installed and configured, it does nothing and sends no data. ats-checker installs neither.

## Development only (not shipped to users)

pytest (MIT), with iniconfig (MIT), pluggy (MIT), packaging (Apache-2.0 OR BSD-2-Clause),
Pygments (BSD-2-Clause).
