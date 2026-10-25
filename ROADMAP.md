# Roadmap

Dogear is an open talking-book maker: books in, navigable audio out, built first for blind
and low-vision listeners and the people who help them.

Each phase lists what it must deliver. A phase is done when every item is built, tested,
and documented.

## Who it's for

- **The listener.** Often someone losing their sight later in life, not a screen-reader power
  user. Listens on a phone app, a talking-book player, or a smart speaker.
- **The producer.** A family member, a volunteer, or a blind user themselves, running Dogear
  on an ordinary computer. The tool itself must be usable with a screen reader.

## Decisions so far

| Decision | Choice | Why |
|---|---|---|
| Name | Dogear | A dog-eared page, plus an ear for listening. |
| Home | `github.com/18hrshift/dogear` | |
| License | Apache-2.0 | Permissive, with a patent grant. Matches the default voice engine (Kokoro). |
| Default voice engine | Kokoro-82M | Apache-2.0, runs on a laptop CPU, the most-downloaded open TTS model on Hugging Face. |
| Hardware baseline | CPU only | A GPU makes it faster, never required. |
| Network | Offline by default | Cloud voices are opt-in and warn that the book text leaves the machine. |

**Open question:** who is the first real listener, and what device do they use? That decides
which output Phase 1 polishes first.

## Phase 0: Foundation

- [ ] Python package skeleton (`src/dogear/`), `pyproject.toml`, `uv` lockfile.
- [ ] `bash test.sh` runs lint plus tests; CI runs it on Linux, macOS, and Windows.
- [ ] Port what works from `18hrshift/audiobook-maker`, with its tests: PDF chapter detection
      cascade (bookmarks, chapter dividers, font size, patterns, page split), text cleanup,
      number and abbreviation expansion, the Tesseract OCR helper, ffmpeg M4B assembly
      (fixing its Windows `which` bug).
- [ ] **Document model.** Extractors output a structured book (sections, headings with levels,
      paragraphs, lists, tables, footnotes, images with alt text, print-page markers, language
      tags), not flat text. Everything downstream works from this.
- [ ] Test fixtures from public-domain books only (Standard Ebooks or Project Gutenberg), with
      the source recorded next to each fixture.
- [ ] `CODE_OF_CONDUCT.md`, issue templates (including an "accessibility barrier" template).

## Phase 1: First listen

Goal: one command turns an EPUB or PDF into a good-sounding M4B on a laptop with no GPU.

- [ ] EPUB and PDF ingest into the document model.
- [ ] Kokoro engine (ONNX, CPU) behind a voice-engine interface.
- [ ] Sentence-level rendering with a cache keyed on text, voice, engine, and settings. A crash
      resumes where it stopped. Fixing one word re-renders only the sentences that contain it.
- [ ] Spoken structure: headings announced, pauses scaled by structure (longer before a new
      chapter), image alt text read as "Image: ...". Footnote and table handling set in config.
- [ ] Loudness normalized across the whole book.
- [ ] Outputs: M4B with chapter markers, cover, and metadata; MP3 folder with an M3U playlist.
- [ ] Screen-reader-friendly CLI: no animated spinners when output isn't a terminal, periodic
      plain-text progress lines ("Chapter 3 of 12 done, about 40 minutes left"), errors that
      say what to do next.
- [ ] Install with one command (`uv tool install` / `pipx install`). Publish to PyPI only once
      this phase works.
- [ ] README sample audio from a public-domain book.

## Phase 2: Talking book

Goal: output a listener can navigate without sight.

- [ ] EPUB 3 with Media Overlays. Sentence-level rendering already gives exact timings for
      every sentence, which is what the SMIL sync files need.
- [ ] DAISY output (2.02 for the widest player support; DAISY 3 to evaluate). Evaluate
      generating it ourselves versus handing EPUB 3 to DAISY Pipeline 2.
- [ ] Navigation by heading level and by print page.
- [ ] User-editable pronunciation dictionary (names, places, jargon).
- [ ] Every output validated in CI: EPUBCheck and Ace by DAISY for EPUB 3, DAISY validators
      for DAISY.
- [ ] Tested by at least one blind or low-vision listener on Thorium Reader and one hardware
      or app player.

## Phase 3: Anyone can run it

Goal: a helper with no Python experience can make a book.

- [ ] Standalone installers for Windows, macOS, and Linux with the default voice bundled.
- [ ] Local web UI, usable from a phone on the same network. Meets WCAG 2.2 AA.
- [ ] Screen-reader test matrix for the UI: NVDA and JAWS (Windows), VoiceOver (macOS, iOS),
      TalkBack (Android), Orca (Linux).
- [ ] Docker image for libraries, schools, and volunteer groups.
- [ ] Plain-language guide written for helpers, not developers.

## Phase 4: More voices and languages

- [ ] Voice engines as plugins. Candidates checked 2026-10-24 (re-check before building):
      Piper (fastest on CPU, many languages, GPL-3.0, so it ships as a separate optional
      package), OmniVoice (Apache-2.0, 600+ languages), Qwen3-TTS (Apache-2.0), Chatterbox (MIT).
- [ ] Cloud voices as opt-in plugins with a clear privacy warning.
- [ ] Language detection per section, so a French quote in an English book gets a French voice.
- [ ] More inputs: DOCX, HTML, Markdown, MOBI/AZW3 via Calibre, automatic OCR for scanned PDFs.

## Ground rules for every phase

- **Accessibility is a requirement, not a feature.** A change that makes Dogear harder to use
  with a screen reader is a bug.
- **No non-commercial or custom-licensed voice as a default.** As of 2026-10-24 that rules out
  Voxtral TTS, F5-TTS, and Fish Speech (non-commercial) and Kitten TTS 2 (custom license).
- **Voice cloning is off by default** and requires the speaker's consent when turned on.
- **No book hosting or sharing.** Docs point print-disabled readers to accessible libraries
  first and explain the legal basics without giving legal advice.
- **Nothing about us without us.** Recruit blind and low-vision testers early, through
  communities like AppleVis, the NVDA forums, and r/Blind.
