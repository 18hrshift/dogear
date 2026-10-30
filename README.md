# Dogear

**An open talking-book maker.** Turn the books you own into audiobooks that blind and
low-vision listeners can actually navigate: by chapter, by heading, by print page.

> **Status: early.** Dogear makes M4B audiobooks, MP3 folders, and talking books (EPUB 3
> and DAISY 2.02, with the text and the narration in step) with a natural-sounding voice
> that runs on an ordinary computer, offline. [`ROADMAP.md`](ROADMAP.md) has the plan.

## Install

There are two ways: an installer, which needs nothing else, or Python.

### With an installer

The installers hold everything Dogear needs: its own Python, ffmpeg, eSpeak NG, and the
voice, so it can make a book without an internet connection. On Windows and Linux they
install Dogear for you alone, with no administrator password. They aren't offered as
downloads yet; until they are, someone comfortable with a terminal can build one (see
below).

- **Windows** (64-bit): run `Dogear-<version>-windows-x86_64-setup.exe`. The installer
  isn't signed yet, so Windows may say "Windows protected your PC". Choose "More info",
  then "Run anyway". The installer can also put the `dogear` command on your PATH. To
  remove Dogear, use Settings, Apps, Installed apps.
- **Mac** (Apple silicon, macOS 14 or newer): open `Dogear-<version>-macos-arm64.dmg` and
  drag Dogear into Applications. Dogear isn't signed by Apple yet, so macOS stops it the
  first time; "Read me first.txt" on the disk image says how to open it.
- **Linux** (64-bit PC): unpack `Dogear-<version>-linux-x86_64.tar.gz`, open a terminal in
  its folder, and run `sh install.sh`. To remove Dogear, run
  `sh ~/.local/opt/dogear/uninstall.sh`.

Choosing Dogear in the Start menu, in Applications, or in your applications menu opens a
window running `dogear serve`, Dogear's web interface: keep that window open while you
use Dogear, and close it to stop Dogear. The web interface is still being built; until
it's in, use the `dogear` command in a terminal (on a Mac, it's
`/Applications/Dogear.app/Contents/Resources/dogear/dogear`).

To build an installer, on the system it's for, from a copy of this repository:

```bash
uv run --no-dev --group installer python packaging/build.py
```

It saves the installer in `dist/`. Each system needs a few build tools as well;
[`packaging/README.md`](packaging/README.md) lists them.

### With Python

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
dogear make mybook.epub --words names.toml  # your own pronunciations (see below)
```

### EPUB talking books

```bash
dogear make mybook.epub --format epub
```

This saves `<book title> talking book.epub`, an EPUB 3 book with the text and the
narration in step (Media Overlays). A reading app that plays them shows the text and
highlights each sentence as it is read, in black on yellow and underlined. In it:

- **A title page**: the book's own, or else the title track (unless
  `announce_title = false`). Then one part per section of the book.
- **A table of contents with every heading**, nested by level. Reading apps move through
  a talking book by its table of contents, so every heading is there.
- **Print page numbers**, when the source book has them: shown where each page begins
  and listed, so an app can go to a page. With `announce_pages = true` they are read
  aloud too, marked so an app can skip them. The book names where the numbers came from:
  the source book's identifier, or its title and authors if it has none.
- **Notes** shown where they are read, **tables** with their column headings, and
  **image descriptions** as text. Dogear keeps no pictures, only their descriptions.
- **Accessibility information** that says what the book has, that its voice is
  synthetic, and that no person has checked it.

[Thorium Reader](https://www.edrlab.org/software/thorium-reader/) (free for Windows,
macOS, and Linux; 3.5.1 is current) plays EPUB talking books. Add the book to its library
and open it to hear it with the text highlighted. Thorium's table of contents takes you
to any heading, and its Go to page command to a print page.

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

### Fix how a word is said

The voice reads most English well, but names and made-up words can come out wrong. You
can fix them in a pronunciation file: a plain text file you write yourself, such as
`names.toml`:

```toml
[words]
Utterson = "utter son"             # the voice reads this spelling instead
"St. John" = "sin jun"             # several words, or a word with a dot, go in quotes
Lanyon = { phonemes = "lˈænjən" }  # exact phonemes, for experts (see below)
```

- Each line under `[words]` is one entry: the word as the book writes it, then how to
  say it. Most entries are a spelling that sounds right: the voice reads "utter son"
  wherever the book says "Utterson".
- A word matches whole and in any capitals: "Utterson" also matches "UTTERSON" and the
  possessive "Utterson's", but not "Uttersons". When the book's word starts with a
  capital, so does the spelling.
- Put the word in quotes if it has spaces, dots, apostrophes, or letters other than A
  to Z (such as "Zoë").
- When entries overlap, the longest wins: with entries for "John" and "St. John",
  "St. John" uses its own.

Use the file for one run with `--words` (`make`, `text`, `words`, and `say` all take
it), or list it in your settings so every book uses it:

```toml
[pronunciation]
files = ["~/names.toml"]
```

When two files list the same word, the later one wins; a `--words` file comes after the
ones in your settings.

To fix a book's words:

1. List the words the voice doesn't know. It guesses these, and they're usually names.
   The first time, this downloads a small language model (about 13 MB), not the whole
   voice.

   ```bash
   dogear words mybook.epub                # all of them, most frequent first
   dogear words mybook.epub --sections 3   # just section 3
   ```

   Each is a numbered line, such as "1. Utterson, 131 times." Words your pronunciation
   files already cover aren't listed.
2. Listen to one in a sentence. `dogear say` speaks the way `dogear make` would and
   saves a WAV file:

   ```bash
   dogear say "Mr. Utterson the lawyer." -o test.wav
   ```

3. If it sounds wrong, add an entry, then listen again with the file:

   ```bash
   dogear say "Mr. Utterson the lawyer." -o test.wav --words names.toml
   ```

4. Make the book with the file. If you made it before, only the sentences whose words
   changed are spoken again; the rest are reused.

`dogear text mybook.epub --spoken --words names.toml` shows every line with your
spellings in place.

**Exact phonemes, for experts.** An entry can give the phonemes the voice should use,
written in the symbols of misaki, the voice's pronunciation dictionary
([the list of symbols](https://github.com/hexgrad/misaki/blob/main/EN_PHONES.md)).
`dogear say "Lanyon" -o test.wav --phonemes` shows the phonemes the voice uses now, a
good place to start. Phoneme entries work with the Kokoro voice only, and only for plain
words (letters, spaces, hyphens, and apostrophes): Dogear spells out abbreviations and
numbers before the voice reads them, so write "Saint John", not "St. John". A symbol the
voice doesn't have stops Dogear with an error that names it.

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
| EPUB 3 with Media Overlays | Read along with highlighted text (low vision, dyslexia) | Works |
| DAISY 2.02 | Talking-book players and apps, with heading and page navigation | Works |

## The voice

Dogear speaks with [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) (Apache-2.0),
an open model small enough to run on a CPU. It has 28 English voices, American and British;
`dogear voices` lists them with Kokoro's own quality grades. The default, `af_heart`, is the
best rated. Pronunciation comes from the dictionaries Kokoro was trained with
([misaki](https://github.com/hexgrad/misaki)), with eSpeak NG for words they don't have.
Your own pronunciation files come first.

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
