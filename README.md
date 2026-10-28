# Dogear

**An open talking-book maker.** Turn the books you own into audiobooks that blind and
low-vision listeners can actually navigate: by chapter, by heading, by print page.

> **Status: early.** Dogear makes M4B audiobooks and MP3 folders with a natural-sounding
> voice that runs on an ordinary computer, offline. Talking-book formats with heading and
> page navigation (DAISY, EPUB 3 read-along) come next. [`ROADMAP.md`](ROADMAP.md) has
> the plan.

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
dogear make mybook.epub --format m4b,mp3  # the M4B and the MP3 folder
dogear make mybook.epub --sections 3      # just section 3, to try the voice first
dogear make mybook.epub --voice bf_emma   # another voice; see `dogear voices`
dogear make mybook.epub --speed 1.0       # faster (the default is 0.9)
dogear make mybook.epub -o ~/Audiobooks   # save somewhere else
dogear make mybook.epub --words names.toml  # your own pronunciations (see below)
```

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

- **Made for listening without sight.** It will produce DAISY talking books and EPUB 3 with
  synchronized audio, not just MP3s. Listeners can jump by heading or print page on players
  like Thorium Reader or a Victor Reader Stream.
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
| DAISY | Talking-book players and apps, with heading and page navigation | Phase 2 |

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
