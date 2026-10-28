# Dogear

**An open talking-book maker.** Turn the books you own into audiobooks that blind and
low-vision listeners can actually navigate: by chapter, by heading, by print page.

> **Status: early.** Dogear makes M4B audiobooks, MP3 folders, and DAISY 2.02 talking
> books with a natural-sounding voice that runs on an ordinary computer, offline. EPUB 3
> read-along output comes next. [`ROADMAP.md`](ROADMAP.md) has the plan.

## Install

Dogear runs on Windows, macOS, and Linux with Python 3.11 or newer. It needs two free
programs first:

| | ffmpeg (audio) | eSpeak NG (pronouncing unusual names) |
|---|---|---|
| Windows | `winget install Gyan.FFmpeg` | `winget install eSpeak-NG.eSpeak-NG` |
| macOS | `brew install ffmpeg` | `brew install espeak-ng` |
| Debian, Ubuntu | `sudo apt install ffmpeg` | `sudo apt install espeak-ng` |

Then install Dogear itself with [uv](https://docs.astral.sh/uv/):

```bash
uv tool install git+https://github.com/18hrshift/dogear-app
```

(`pipx install git+https://github.com/18hrshift/dogear-app` works too.) Dogear isn't on PyPI
yet. Don't `pip install dogear`: that name on PyPI belongs to a different project. For Kindle books, also install [Calibre](https://calibre-ebook.com). For scanned PDFs,
install Tesseract OCR.

## Make an audiobook

```bash
dogear make mybook.epub
```

That's it. Dogear saves `<book title>.m4b` next to the book, with a chapter marker for every
chapter, the cover, and the title and author filled in. The first time, it downloads the
voice (about 340 MB, once).

It takes a while. On a 6-core desktop processor from 2017 (Intel i7-8700K), Dogear spoke
about three times faster than real time, so an hour of audio took about 20 minutes. It
prints a plain progress line now and then, with an estimate of the time left. **Stopping
is safe**: press Ctrl+C, run the same command later, and it carries on where it stopped.
Every spoken sentence is kept, so fixing one word in a book re-speaks only the sentences
that contain it.

Useful options:

```bash
dogear make mybook.epub --format mp3      # a folder of numbered MP3s plus a playlist
dogear make mybook.epub --format daisy    # a DAISY talking book (see below)
dogear make mybook.epub --format m4b,mp3  # the M4B and the MP3 folder
dogear make mybook.epub --sections 3      # just section 3, to try the voice first
dogear make mybook.epub --voice bf_emma   # another voice; see `dogear voices`
dogear make mybook.epub --speed 1.0       # faster (the default is 0.9)
dogear make mybook.epub -o ~/Audiobooks   # save somewhere else
```

### DAISY talking books

`dogear make mybook.epub --format daisy` saves a folder named `<book title> DAISY` that
holds a DAISY 2.02 talking book, with the full text and the full audio:

- `ncc.html`, the book's map: every heading, at its level, and every print page.
- For each section, an MP3 file, its text as an `.html` file, and a `.smil` file that
  ties each sentence of the text to the stretch of audio that reads it.

A listener can move by heading level and by print page, and an app that shows the text
highlights each sentence as it's read. Page numbers read aloud (`announce_pages = true`)
are marked so that players that let you turn page numbers off can skip them.

To listen:

- **Thorium Reader**, a free reading app for Windows, macOS, and Linux: open `ncc.html`
  from the folder.
- **Dolphin EasyReader**: zip the folder and import the zip.
- **A DAISY player**, such as a Victor Reader Stream or a Plextalk Pocket: copy the whole
  folder to the player's memory card, where its manual says talking books go.

These all list DAISY 2.02 among the formats they read. Dogear's DAISY books pass the
DAISY Pipeline 2 validator, but they haven't been tried on these players yet. If you try
one, please tell us how it went.

### Check a book before making it

```bash
dogear outline mybook.epub                # title, authors, and every section
dogear text mybook.epub --section 3       # the text Dogear found in section 3
dogear text mybook.epub --spoken          # every line exactly as the voice will say it
dogear ocr scanned.pdf                    # add a text layer to a scanned PDF (needs Tesseract)
dogear download                           # fetch the voice now, before going offline
```

Everything Dogear prints is plain text, written to read well with a screen reader.

### What it reads, and how

- **EPUB, PDF, and Kindle** (MOBI and AZW3, through Calibre). EPUB chapters come from the
  book's table of contents.
- **A title track** opens the book with its title and who wrote it.
- **Headings** are read with a pause after them. Longer pauses mark bigger breaks: a
  sentence, a paragraph, a scene break, a chapter.
- **Image descriptions** are read as "Image: ...". Decorative images are skipped.
- **Footnotes** are read right after the paragraph that refers to them.
- **Tables** are read row by row, with each column's heading.
- **Numbers, dates, money, times, and units** are spoken the way a person would say them:
  "$5.99" is "five dollars and ninety-nine cents", "Chapter IV" is "Chapter four".
- **Print page numbers** are kept for navigation and not read aloud, unless you ask.

Every one of these is a setting. Put the ones you want to change in a TOML file and pass
it with `--config`:

```toml
[voice]
voice = "bf_emma"
speed = 1.0

[narration]
footnotes = "end_of_section"   # or "after_paragraph", "where_printed", "skip"
announce_pages = true          # say "Page 42" where each print page begins
```

The full list, with what each one does, is in
[`src/dogear/defaults.toml`](src/dogear/defaults.toml).

## Why another audiobook tool?

There are good ebook-to-audiobook converters already. None of them are built for people who
can't see the screen. Dogear is:

- **Made for listening without sight.** It makes DAISY talking books, not just MP3s, and
  EPUB 3 with synchronized audio is next. Listeners can jump by heading or by print page.
- **Structure-aware.** Headings, image descriptions, footnotes, and tables are read on purpose,
  not dumped as a wall of text. Page numbers become navigation points instead of being spoken.
- **Offline and CPU-first.** A normal computer is enough. No GPU, no account, and your books
  never leave your machine.
- **Accessible to run.** The command line, and the web interface planned for later, are
  designed to work with screen readers (NVDA, JAWS, VoiceOver, TalkBack, Orca).

## Outputs

| Format | Good for | Status |
|---|---|---|
| M4B with chapters | Phone audiobook apps | Works |
| MP3 folder + playlist | Anything that plays audio, including older players | Works |
| EPUB 3 with Media Overlays | Read along with highlighted text (low vision, dyslexia) | Phase 2 |
| DAISY 2.02 | Talking-book players and apps, with heading and page navigation | Works |

## The voice

Dogear speaks with [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) (Apache-2.0),
an open model small enough to run on a CPU. It has 28 English voices, American and British;
`dogear voices` lists them with Kokoro's own quality grades. The default, `af_heart`, is the
best rated. Pronunciation comes from the dictionaries Kokoro was trained with
([misaki](https://github.com/hexgrad/misaki)), with eSpeak NG for words they don't have.

## Get involved

We especially want **blind and low-vision testers** from the start. See
[`CONTRIBUTING.md`](CONTRIBUTING.md).

## A note on books and copyright

Dogear is for converting books you have the right to convert. It has no hosting or sharing
features. If you are print-disabled, check accessible libraries first (for example Bookshare,
or your national library service for the blind). Many books already exist in accessible
formats there.

## Origins

Dogear grew out of [`18hrshift/audiobook-maker`](https://github.com/18hrshift/audiobook-maker),
a personal PDF-to-audiobook tool. Its chapter detection and text cleanup are the starting point.

## License

[Apache-2.0](LICENSE).
