# Test fixtures

Only public-domain books belong here, each listed below with where it came from. Tests read
these files only through Dogear's extractors, never by unpacking them.

| File | Title | Author | Source | License | Fetched | SHA-256 |
|---|---|---|---|---|---|---|
| `robert-louis-stevenson_the-strange-case-of-dr-jekyll-and-mr-hyde.epub` | The Strange Case of Dr. Jekyll and Mr. Hyde (Standard Ebooks edition) | Robert Louis Stevenson | <https://standardebooks.org/ebooks/robert-louis-stevenson/the-strange-case-of-dr-jekyll-and-mr-hyde> (the "compatible epub" download) | Text in the US public domain; Standard Ebooks dedicates its edition to the public domain under CC0 1.0 | 2026-10-24 | `9f0306972d1c6a21dcdf0be8a752a58a42f7470fda0613c4dc40090923f08adc` |

Used by `tests/test_epub.py::test_standard_ebooks_jekyll_and_hyde`.

## Generated at test time

PDF fixtures are not stored here. `tests/pdf_builder.py` builds them with reportlab during
the tests, using text from *Alice's Adventures in Wonderland* by Lewis Carroll (Project
Gutenberg #11, public domain in the US). OCR and audio tests generate their own inputs too.
