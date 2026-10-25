# HANDOFF: Phase 0, paused 2026-10-24

Phase 0 of [`ROADMAP.md`](ROADMAP.md) was paused partway. This note says what's done, what
isn't, and what to do next. Delete it when Phase 0 merges to `main`.

- **Branch:** `wip/phase-0` (pushed). `main` still has only the planning docs.
- **Read first:** [`AGENTS.md`](AGENTS.md) (project rules), then this file.
- **Run:** `uv sync`, then `bash test.sh` (ruff check, ruff format check, pytest).
- **Old code being ported:** [`18hrshift/audiobook-maker`](https://github.com/18hrshift/audiobook-maker).

## State

| Area | Files | State |
|---|---|---|
| Package, config, CI | `pyproject.toml`, `uv.lock`, `test.sh`, `src/dogear/config.py`, `defaults.toml`, `.github/` | Done, tested |
| Document model | `src/dogear/document.py` | Done, tested |
| Errors, external tools | `errors.py`, `tools.py` | Done, tested |
| Speech text | `speech/sentences.py`, `speech/normalize.py` | Done, tested |
| Audio (ffmpeg) | `audio.py` | Done, tested |
| OCR (Tesseract) | `ocr.py` | Done, tested with real Tesseract |
| CLI | `cli.py`: `outline`, `text [--spoken]`, `ocr` | Done, tested with a stub book |
| Issue templates | `.github/ISSUE_TEMPLATE/` | Done |
| **EPUB extractor** | `extract/epub.py`, `epub_package.py`, `epub_nav.py`, `safe_xml.py`, `xhtml.py`, `xhtml_blocks.py` | **Written, no tests, not reviewed** |
| **PDF extractor** | `extract/pdf.py`, `pdf_chapters.py`, `pdf_sections.py`, `pdf_text.py` | **Written, no tests, not reviewed** |
| **Kindle via Calibre** | `extract/calibre.py` | **Written, no tests, not reviewed** |
| Docs for Phase 0 | `README.md`, `ROADMAP.md`, `AGENTS.md` | **Not updated** |
| Code of conduct | `CODE_OF_CONDUCT.md` | **Blocked:** needs a contact address from the owner |

84 tests pass. All of them cover the "Done" rows; none touch the extractors yet.
`ruff check .` reports 3 line-length errors, all in the unreviewed extractor files.

The extractors were written by two agents that were stopped before they wrote tests or
reports. They import cleanly. Nothing else about them is verified.

## Next steps, in order

1. **Review and test the EPUB extractor** against the spec below. Add `tests/epub_builder.py`
   (writes synthetic EPUBs) and `tests/test_epub.py`.
2. **Review and test the PDF extractor** against the spec below. Add `tests/pdf_builder.py`
   (builds PDFs at test time with reportlab; don't commit PDFs) and `tests/test_pdf*.py`.
3. **Test `calibre.py`** with monkeypatched `find_tool`/`run_tool`, plus one test using
   `require_tool("ebook-convert")`.
4. **Real-world fixture:** one short public-domain EPUB from Standard Ebooks (CC0), under about
   600 KB, in `tests/fixtures/`, listed in a new `tests/fixtures/README.md` with title, author,
   source URL, license, date fetched, and sha256. The folder is empty now.
5. **End-to-end CLI test:** `dogear outline` and `dogear text --spoken` on a built EPUB and PDF.
6. **Fix lint** so `bash test.sh` passes.
7. **Docs:**
   - README status: Phase 0 done; install from source; the three commands.
   - Tick the Phase 0 items in ROADMAP.
   - AGENTS.md: module layout, current state, and the dependency license note (below).
8. **Code of conduct:** Contributor Covenant 2.1, once the owner gives a contact address.
9. **Merge:** open a PR from `wip/phase-0` to `main`, check CI passes on all six jobs
   (Linux, macOS, Windows x Python 3.11 and 3.13), merge, delete this file.

## Extractor specs (what the code should do; verify each with a test)

### EPUB
- Read the zip directly; never unpack it to disk. Resolve hrefs relative to the OPF, URL-decode
  them, and treat a path that escapes the archive as missing.
- **Untrusted input:** no external entities, no network, no DTD loading (`safe_xml.py`).
  `&nbsp;` and `&mdash;` must still come out as the right characters. Test that an XXE payload
  pointing at a local file does not leak it.
- **Metadata:** first dc:title (else file stem), all dc:creator in order, dc:language, the
  dc:identifier named by `unique-identifier`, dc:publisher.
- **Reading order:** spine, skipping `linear="no"` and non-XHTML items. The EPUB 3 nav document
  is not read as content (log it), but it is parsed for TOC titles, landmarks, and page-list.
  EPUB 2 NCX is used when there's no nav doc.
- **Section title:** TOC entry, else first heading, else "Section N".
- **Kind:** explicit frontmatter/bodymatter/backmatter epub:type wins, then landmarks, then
  specific types (cover, titlepage, toc, dedication, epigraph, foreword, preface: front;
  appendix, colophon, index, glossary, bibliography, endnotes: back). Default: body.
- **Blocks:**
  - h1-h6 and `role="heading"`: Heading
  - p, and loose text in containers: Paragraph (`br` becomes a newline)
  - ul/ol: ListBlock
  - table: Table (header rows from thead or all-th rows, plus caption)
  - img: Image (`alt=None` if the attribute is missing, `""` if empty); figure plus figcaption: caption
  - pagebreak epub:type or `doc-pagebreak`: PageMarker
  - footnote/endnote/rearnote: Footnote, with backlinks stripped
  - noterefs: the id goes into the paragraph's `note_refs`, and the marker text is removed
- **Language:** inherited from `xml:lang` or `lang`. A block's `lang` is set only when it
  differs from its section's.
- **Errors:** damaged or missing container or OPF, DRM (encryption.xml covering content, not
  just fonts), or a book with no sections: ExtractionError with a hint.

### PDF
- Use pypdf (metadata, outline, page labels, encryption) and pdfplumber (lines, positions,
  font sizes). Read each page once and reuse that data for every method.
- **Cascade** in `config["pdf"]["chapter_detection"]` order. The first method that finds 2+
  boundaries wins:
  - bookmarks
  - chapter_dividers ("Chapter N" with digits, roman numerals, or number words)
  - font_size (`heading_size_ratio` x body size)
  - pattern
  - page_split ("Part N")

  An unknown method name is a ConfigError.
- **Sections:** pages before the first boundary become a front section. Back-matter headings
  (acknowledgments, bibliography, notes, index, appendix, ...) start back sections. Front and
  back matter is classified, never dropped.
- **Blocks:** a PageMarker at each page (printed label if the PDF defines labels, else the page
  number), then paragraphs. A section's opening heading becomes a Heading, not a duplicate
  paragraph.
- **Cleanup:**
  - drop bare page numbers
  - drop running headers and footers (thresholds are in `[pdf]` in `defaults.toml`, added by
    the PDF agent: review them)
  - rejoin line-end hyphenation
- **Paragraphs:** split by line gaps and first-line indents. A paragraph that runs across a page
  is merged, with the next page's marker placed *before* it, so jumping to a page lands early,
  never late.
- **Errors:**
  - Too little text per page: ScannedPdfError with the hint "Run `dogear ocr <file>` first to
    add a text layer, then open the new file."
  - An encrypted PDF an empty password can't open: ExtractionError.
  - A damaged file: ExtractionError.

## Decisions made in Phase 0

- **No AGPL in core.** The old repo's PyMuPDF and EbookLib are AGPL. They were replaced with
  pdfplumber (MIT), pypdf (BSD), pypdfium2 (BSD/Apache), and zip + lxml (BSD).
- **num2words is LGPL-2.1.** It's used unmodified, which is fine with Apache-2.0. Record it in
  AGENTS.md. All other runtime dependencies are MIT, BSD, Apache, or MIT-CMU (checked with
  `uv tree`).
- **Display text vs spoken text.** The document model stores display text only. Abbreviations,
  numbers, and quotes are rewritten per sentence at speech time, so read-along output can show
  the original words.
- **The sentence is the unit.** Splitting happens on display text. Abbreviation-aware rules come
  from config (`no_sentence_break_after`, plus the title and before-number tables). Overlong
  sentences split at clauses, then at spaces, never mid-word.
- **Speech rules:**
  - Abbreviations live in three config tables: always expanded, only before a name, and only
    before a number. That fixes "He said no." becoming "He said number".
  - Four-digit numbers 1100 to 2099 are read as years.
  - Long ungrouped numbers and leading zeros are read digit by digit.
  - Decimal digits are read one at a time.
- **Front and back matter is kept** and classified, unlike the old repo, which dropped it.
- **CI:** actions are pinned to commit SHAs. `DOGEAR_REQUIRE_TOOLS=ffmpeg,ffprobe,tesseract`
  makes those tests fail instead of skip on CI. Calibre isn't installed on CI, so its
  integration test skips.
- **The PyPI name `dogear` is free** but deliberately not claimed. Publish when Phase 1 works.
- **Commits** use the 18hrshift GitHub private (noreply) email address.

## Open questions for the owner

- Contact address for the code of conduct.
- Who is the first real listener, and what device do they use? This decides what Phase 1
  polishes first.
