# AGENTS.md

Rules for coding agents (Claude Code, Codex, OpenCode, Cursor, etc.) and humans working on Dogear.

## What this is

Dogear is an open talking-book maker: books in, navigable audio out, built first for blind
and low-vision listeners. Read [`ROADMAP.md`](ROADMAP.md) before starting work. It defines
each phase and what "done" means.

**Current state (2026-10-24):** planning only. No code yet. Phase 0 is next.

## Project rules

1. **Accessibility is a requirement.** Every user-facing surface (CLI output, error messages,
   web UI, docs) must work with a screen reader. In the CLI: no animated spinners when stdout
   isn't a terminal, plain progress lines, and errors that say what to do next. Web UI
   targets WCAG 2.2 AA.
2. **Structure, not text dumps.** Extractors produce the structured document model (headings
   with levels, footnotes, images with alt text, print-page markers, language). Never
   flatten to plain text before the speech stage.
3. **Licenses matter.** Core code is Apache-2.0. Don't add a GPL dependency to the core
   package; GPL engines (for example Piper) ship as separate optional packages. Never make a
   non-commercial or custom-licensed voice the default. Record each engine's license in the docs.
4. **Offline by default.** Anything that sends book text off the machine is opt-in and warns first.
5. **Config is the single source of truth.** Paths, model IDs, engine settings, and defaults
   live in config and are read from there. A test should prove changing the config changes
   behavior.
6. **Small modules.** One job per module: an extractor per format, an engine per voice
   backend, a packager per output format.
7. **Fail loudly.** Raise with a clear message. Never swallow errors or silently skip content.
8. **Test what you build.** `bash test.sh` must pass before every merge (arrives in Phase 0).
   Voice engines are tested with mocks; CI never needs a GPU or an API key.
9. **Docs are claims.** Don't document a command, flag, or format that isn't built. When you
   finish a roadmap item, tick it in `ROADMAP.md` in the same commit.
10. **No secrets, no books.** API keys go in `.env` (gitignored). Only public-domain books go
    in the repo, with their source noted. Never commit generated audio.

## Prior art

Dogear grew out of `github.com/18hrshift/audiobook-maker`. Its `AGENTS.md` lists which parts
work (chapter detection, text cleanup) and which don't (all three of its TTS backends).
Port the working parts with their tests; rewrite the rest.
