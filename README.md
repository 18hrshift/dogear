# Dogear

**An open talking-book maker.** Turn the books you own into audiobooks that blind and
low-vision listeners can actually navigate: by chapter, by heading, by print page.

> **Status: early.** Dogear can read books and prepare their text, but it **does not make
> audio yet**; voices arrive in Phase 1. The rest of this README describes what Dogear is
> being built to do. [`ROADMAP.md`](ROADMAP.md) has the plan.

## What works today

Dogear reads EPUB and PDF files (and Kindle MOBI/AZW3, if [Calibre](https://calibre-ebook.com)
is installed) into chapters, headings, notes, image descriptions, and print page numbers.

```bash
git clone https://github.com/18hrshift/dogear && cd dogear
uv sync                                    # needs uv: https://docs.astral.sh/uv/

uv run dogear outline mybook.epub          # title, authors, and every section
uv run dogear text mybook.epub --section 3 # the text Dogear found in section 3
uv run dogear text mybook.epub --spoken    # each sentence the way the voice will say it
uv run dogear ocr scanned.pdf              # add a text layer to a scanned PDF (needs Tesseract)
```

Output is plain text written to read well with a screen reader.

## Why another audiobook tool?

There are good ebook-to-audiobook converters already. None of them are built for people who
can't see the screen. Dogear is:

- **Made for listening without sight.** It will produce DAISY talking books and EPUB 3 with
  synchronized audio, not just MP3s. Listeners can jump by heading or print page on players
  like Thorium Reader or a Victor Reader Stream.
- **Structure-aware.** Headings, image descriptions, footnotes, and tables are read on purpose,
  not dumped as a wall of text. Page numbers become navigation points instead of being spoken.
- **Offline and CPU-first.** A normal laptop is enough. No GPU, no account, and your books
  never leave your machine unless you choose a cloud voice.
- **Accessible to run.** The command line and the future web UI are designed to work with
  screen readers (NVDA, JAWS, VoiceOver, TalkBack, Orca).

## Planned outputs

| Format | Good for |
|---|---|
| M4B with chapters | Phone audiobook apps |
| MP3 folder + playlist | Anything that plays audio, including older players |
| EPUB 3 with Media Overlays | Read along with highlighted text (low vision, dyslexia) |
| DAISY | Talking-book players and apps, with heading and page navigation |

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
