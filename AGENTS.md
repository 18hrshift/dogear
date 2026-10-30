# AGENTS.md

Rules for coding agents (Claude Code, Codex, OpenCode, Cursor, etc.) and humans working on Dogear.

## What this is

Dogear is an open talking-book maker: books in, navigable audio out, built first for blind
and low-vision listeners. Read [`ROADMAP.md`](ROADMAP.md) before starting work. It defines
each phase and what "done" means.

**Current state:** Phase 2 (talking book). `dogear make` reads an EPUB, PDF, or Kindle book
into a structured document, narrates it with spoken structure, speaks it with the Kokoro
voice on the CPU, and packages an M4B, an MP3 folder, an EPUB 3 talking book, and/or a
DAISY 2.02 talking book. Phase 3 has begun: `dogear serve` is a local web page that does
the same from a browser, running `dogear` itself as a child process for each book.

## Working here

```bash
uv sync             # install, including dev tools
bash test.sh        # ruff check + ruff format check + pytest; must pass before every merge
uv run dogear --help
```

Some tests need ffmpeg, Tesseract, or eSpeak NG and skip without them. CI installs all three
and sets `DOGEAR_REQUIRE_TOOLS=ffmpeg,ffprobe,tesseract,espeak-ng`, which turns those skips
into failures. Unit tests never load the real voice; a separate CI job (`voice`) downloads
it (cached between runs) and makes a short audiobook on each platform.

DAISY output is validated outside pytest, with DAISY Pipeline 2 in Docker:

```bash
uv run python tests/daisy_samples.py /tmp/daisy        # sample books, with a fake voice
scripts/check-daisy.sh /tmp/daisy/*/*DAISY             # exits 0 only if every book passes
```

The web page is checked for accessibility outside pytest too, with axe-core in a real
browser. The script makes every page in every state with test data (no voice needed):

```bash
scripts/check-web-a11y.sh /tmp/web-pages               # exits 0 only if every page passes
```

Axe catches only some WCAG failures. When you change a page, also check it by hand: with
the keyboard alone, with a screen reader, at 320 CSS pixels wide, and with text at 200%.

## Layout

| Path | Job |
|---|---|
| `src/dogear/document.py` | The structured book every stage reads: sections and blocks (headings, paragraphs, lists, tables, images, notes, page markers). Display text only. |
| `src/dogear/defaults.toml`, `config.py` | Every default setting, and loading and validating a user's TOML on top. |
| `src/dogear/errors.py` | Errors a user can fix, each with a hint. Anything else is a bug. |
| `src/dogear/tools.py` | Finding and running ffmpeg, Tesseract, and Calibre with install hints. |
| `src/dogear/file_lock.py` | An exclusive lock on a file (flock, or msvcrt.locking on Windows) that the system lets go of when the process ends, however it ends. Keeps a second `dogear serve` off a web folder in use, and `dogear make` off another run's work folder. |
| `src/dogear/extract/` | One module per format: `epub.py` (+ `epub_package`, `epub_nav`, `epub_sections` for sections from the table of contents, `epub_kind`, `epub_cover`, `xhtml`, `xhtml_blocks`, `xhtml_split`, `safe_xml`), `pdf.py` (+ `pdf_page`, `pdf_text`, `pdf_furniture` for running headers, `pdf_columns`, `pdf_notes` for page-foot footnotes, `pdf_headings`, `pdf_figures`, `pdf_hyphens`, `pdf_chapters`, `pdf_sections`), `calibre.py` for Kindle. |
| `src/dogear/speech/` | `sentences.py` splits display text into sentences; `normalize.py` rewrites a sentence into what the voice should say, with `money`, `times`, `units`, and `roman` handling one kind of text each. |
| `src/dogear/narration.py` | Spoken structure: a section becomes utterances with pauses (headings, image descriptions, notes, tables, scene breaks), per `[narration]`, plus passages that say which utterances read which block. Also the title track. |
| `src/dogear/voice/` | Voice engines. `engine.py` is the interface (`plan` is cheap and gives the cache key; `render` makes audio). `kokoro.py` runs Kokoro with onnxruntime; `g2p.py` turns English into phonemes (misaki, plus the espeak-ng program for unknown words); `downloads.py` and `catalog.toml` fetch model files pinned by SHA-256. |
| `src/dogear/render/` | Speaking a narrated book into one WAV per section, through the sentence cache (`cache.py`), with plain-text progress (`progress.py`). Records where each utterance starts in the audio. `work.py` is each run's own folder under `<cache>/work`, locked while the run lasts, and clears away the folders of runs that died. |
| `src/dogear/readalong/` | Talking-book text: `build.py` turns passages and audio timings into text items with ids and syncs (`model.py`), shared by the EPUB 3 and DAISY packagers; `outline.py` settles heading levels across the book and sorts page numbers. |
| `src/dogear/output/` | Packaging, one module per job: `loudness` (one gain per chapter to a target, with a capped limiter), `m4b`, `mp3_folder` with `playlist` and safe `filenames`, `tags`, `cover`, and `folder_record` (so a re-run replaces only its own files). `talking_audio` encodes talking-book MP3s; `book_identity` gives their identifier and narrator. The EPUB 3 talking book is `epub3` (putting it together, written next to the output and moved into place), with `epub3_text` (a section's content document), `epub3_smil` (its Media Overlay), `epub3_nav` (contents, page list, landmarks), `epub3_package` (the package document), `epub3_a11y` (accessibility claims decided from the content), `epub3_container` (the zip), `epub3_xhtml` (what the XHTML documents share), and `epub3.css`; `language_tag` checks a book's language tags before they go into markup. DAISY 2.02: `daisy202` puts the book in its folder; `daisy202_plan` names the files and settles the metadata and times; `daisy202_clock` rounds clip times to milliseconds and writes them; `daisy202_xhtml` is the XHTML 1.0 skeleton; `daisy202_text`, `daisy202_smil`, and `daisy202_ncc` write the text documents, SMIL files, and NCC. |
| `src/dogear/make.py` | `dogear make` from start to finish: extract, narrate, speak, package. |
| `src/dogear/pronunciations.py` | The user's pronunciation files (`[pronunciation]`, `--words`): reading and checking them. `speech/word_match.py` finds their words in text. Sounds-like entries are applied first in `speech/normalize.py`; phoneme entries are pinned in `voice/g2p.py` and checked against Kokoro's symbols in `voice/kokoro.py`. |
| `src/dogear/unknown_words.py` | `dogear words`: the words the voice would hand to espeak-ng, most frequent first. Needs spaCy's model, not the Kokoro voice. |
| `src/dogear/say.py` | `dogear say`: a short text spoken into a WAV file through the same normalization, voice, and renderer as `dogear make`. |
| `src/dogear/paths.py` | Per-user folders for downloaded models, the speech cache, and the web page's books. |
| `src/dogear/ocr.py` | Adding a text layer to scanned PDFs. |
| `src/dogear/book_summary.py` | The facts `dogear outline` gives (title, authors, and each section's kind, words, print pages, and counts of images, notes, and tables), in words and as JSON (`outline --json`), and reading that JSON back with every field checked. |
| `src/dogear/cli.py`, `__main__.py` | The `dogear` command, also run as `python -m dogear`. |
| `src/dogear/web/` | `dogear serve`, the local web page, one module per job. `server` starts it, prints the links, and stops on Ctrl+C; `settings` is `[web]` plus the command's options, and the server locks the web folder while it runs; `app` wires the routes, checks, and queues. Checks: `guard` (Host on this computer only, same-origin forms, the access cookie), `headers` (security headers), `access_key` (the key file, comparing keys, slowing wrong ones). Pages: `access_pages`, `book_pages`, `site_pages`, rendered by `templating` from `templates/` (Jinja2, autoescaped), with `static/` (one stylesheet, and `progress.js`, which only adds live updates). `forms` reads small forms with a bound; `uploads` streams a book to disk with the size limit; `choices` is the choose form; `status` puts a book's state in words; `downloads` serves outputs and cached zips. Work: `books` (each book's record and folder, saved with `atomic`), `library` (the books and two queues, reading and making), `worker` (a queue that runs one job at a time), `child` (running `dogear` as a child process, never a book in the server), `reading` (`outline --json`, checked) and `making` (`make`, its progress, and what it saved). |
| `scripts/check-epub.sh` | Checks an EPUB with EPUBCheck 5.4.0 (`--failonwarnings`) and Ace 1.4.6 (`-E`), downloading both pinned into `$DOGEAR_VALIDATORS` (default `~/.cache/dogear-validators`). Reports go next to the book. |
| `scripts/make-sample-epub.py` | Makes two sample EPUB talking books with a fake voice. Between them they use every kind of block, with pages announced and not, tables read and skipped, and the title track on and off. Check them with `check-epub.sh`. |
| `scripts/check-daisy.sh` | Validates DAISY 2.02 books with DAISY Pipeline 2's `daisy202-validator` (pinned Docker image), saving its report next to each book. Used locally and in CI. |
| `tests/daisy_samples.py`, `tests/dtd/` | A book with every kind of block, made into DAISY books through `dogear make` with a fake voice; and the W3C XHTML 1.0 and SMIL 1.0 DTDs the unit tests validate against, offline. |
| `scripts/check-web-a11y.sh`, `scripts/web-a11y.cjs` | Checks every web page in every state with axe-core 4.14.0 in Playwright 1.64.1's headless Chromium (pinned, downloaded into `$DOGEAR_VALIDATORS`): desktop and 320 pixels wide, light and dark, plus no sideways scrolling with text at 200% and a focus ring on everything Tab reaches. Used locally and in CI. |
| `tests/web_samples.py`, `tests/fake_dogear.py` | The web app with books in every state, each page saved as HTML (for the unit tests and `check-web-a11y.sh`); and a stand-in `dogear` command the web tests run as the child process. |
| `Dockerfile`, `docker/` | The Docker image: Dogear, ffmpeg, eSpeak NG, Tesseract, and the default voice, running `dogear serve --lan` with everything it keeps on a `/data` volume. `docker/config.toml` is its settings file (via `DOGEAR_CONFIG`); `docker/README.md` is the guide. The `Docker` workflow builds it and makes a book offline with it. |

## Project rules

1. **Accessibility is a requirement.** Every user-facing surface (CLI output, error messages,
   web UI, docs) must work with a screen reader. In the CLI: plain sentences and numbered
   lists, no tables, colors, or animations, progress as occasional plain lines, and errors
   that say what to do next. Web UI targets WCAG 2.2 AA.
2. **Structure, not text dumps.** Extractors produce the structured document model. Never
   flatten to plain text before the speech stage. The model holds display text; spoken forms
   are made per sentence in `speech/` and never stored.
3. **Licenses matter.** Core code is Apache-2.0. No GPL or AGPL dependency in the core
   package (PyMuPDF and EbookLib were rejected for being AGPL); GPL engines such as Piper
   ship as separate optional packages. LGPL is allowed only when used unmodified, and must
   be listed below. Never make a non-commercial or custom-licensed voice the default.
4. **Book files are untrusted input.** Never unpack them to disk, never let them trigger
   network access or external entities, and bound anything a file can make large.
5. **Offline by default.** Anything that sends book text off the machine is opt-in and warns first.
6. **Config is the single source of truth.** Defaults live only in `defaults.toml` and are
   read from the loaded config. A test should prove changing a setting changes behavior.
7. **Small modules.** One job per module: an extractor per format, an engine per voice
   backend, a packager per output format.
8. **Fail loudly.** Raise with a clear message. Never swallow errors or silently drop content:
   front and back matter are classified, not removed.
9. **Test what you build.** Voice engines are tested with mocks; CI never needs a GPU or an
   API key.
10. **Docs are claims.** Don't document a command, flag, or format that isn't built. When you
    finish a roadmap item, tick it in `ROADMAP.md` in the same commit.
11. **No secrets, no books.** API keys go in `.env` (gitignored). Only public-domain books go
    in the repo, listed in `tests/fixtures/README.md`. Never commit generated audio.

## Runtime dependency licenses

Checked with `uv tree --no-dev` when added. Recheck when adding or upgrading.

| Package | License | Used for |
|---|---|---|
| lxml | BSD-3-Clause | EPUB and XHTML parsing |
| pdfplumber, pdfminer.six | MIT | PDF text, positions, font sizes |
| pypdf | BSD-3-Clause | PDF outline, page labels, merging |
| pypdfium2 | BSD-3-Clause / Apache-2.0 | Rendering PDF pages for OCR |
| Pillow | MIT-CMU | Page images for OCR |
| num2words (+ docopt, MIT) | **LGPL-2.1**, used unmodified | Numbers to words |
| cryptography, charset-normalizer, cffi, pycparser | Apache-2.0 or BSD / MIT | pdfminer.six dependencies |
| onnxruntime (+ flatbuffers, protobuf, packaging) | MIT (Apache-2.0, BSD-3-Clause) | Running the Kokoro model |
| numpy | BSD-3-Clause | Audio samples |
| misaki (+ addict, regex) | Apache-2.0 (MIT, Apache-2.0) | English phonemes for Kokoro. Installed without its `en` extra, which pulls in GPL phonemizer and espeak-ng libraries. |
| spaCy and its dependencies (thinc, pydantic, typer, requests, and others) | MIT, BSD, Apache-2.0, ISC, PSF; **tqdm and certifi are MPL-2.0**, used unmodified | Part-of-speech tags, so heteronyms are pronounced right |
| Starlette (+ anyio, idna, typing-extensions) | BSD-3-Clause (MIT, BSD-3-Clause, PSF) | The web page's routes, requests, and responses |
| uvicorn (+ click, h11) | BSD-3-Clause (BSD-3-Clause, MIT) | Serving the web page |
| Jinja2 (+ MarkupSafe) | BSD-3-Clause | The web page's HTML templates, autoescaped |
| python-multipart | Apache-2.0 | Reading a book upload as it streams in |

Downloaded on first use, not bundled: the Kokoro-82M model and voices (Apache-2.0) and spaCy's
`en_core_web_sm` model (MIT), each pinned by SHA-256 in `src/dogear/voice/catalog.toml`.

External programs (not bundled, run as separate processes, never linked): ffmpeg, Tesseract,
Calibre, and eSpeak NG (GPL-3.0, used only for words misaki's dictionaries don't have, the
same fallback Kokoro's own pipeline uses).

CI only, never needed to run Dogear: DAISY Pipeline 2 (LGPL-3.0), run from its Docker image
by `scripts/check-daisy.sh` to validate DAISY output; Playwright (Apache-2.0), its Chromium,
and axe-core (MPL-2.0), downloaded by `scripts/check-web-a11y.sh` to check the web page.
The web tests use httpx2 (BSD-3-Clause), a dev dependency, for Starlette's test client.

## Prior art

Dogear grew out of `github.com/18hrshift/audiobook-maker`. Phase 0 ported its chapter
detection, text cleanup, number and abbreviation expansion, OCR, and M4B assembly, and
fixed bugs found on the way. Its TTS backends were not ported (all three were broken).
