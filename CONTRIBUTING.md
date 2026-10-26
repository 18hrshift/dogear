# Contributing to Dogear

Thanks for helping. Dogear is early (Phase 0 of [`ROADMAP.md`](ROADMAP.md)), so feedback on
the roadmap is as useful as code.

## If you are blind or have low vision

You are who this is for, and we want to hear from you before we build the wrong thing.
Open an issue (there's an "Accessibility barrier" form) or start a discussion about:

- Which players and apps you use for books (phone app, DAISY player, smart speaker, other).
- What makes an audiobook hard to navigate or listen to.
- Anything in Dogear's docs, output, or tools that doesn't work with your screen reader.
  We treat that as a bug.

## If you write code

You need [uv](https://docs.astral.sh/uv/) and Python 3.11 or newer. Some tests also use
ffmpeg and Tesseract; they skip if those aren't installed.

```bash
git clone https://github.com/18hrshift/dogear
cd dogear
uv sync
bash test.sh        # lint, format check, and tests; must pass before every merge
uv run dogear --help
```

Read [`AGENTS.md`](AGENTS.md) first. It holds the project rules for humans and coding agents
alike, including which licenses a new dependency may have.

## Books in this repo

Only public-domain texts go in the repo, for tests and samples. Note where each one came from
in `tests/fixtures/README.md`. Never commit a book you don't have the rights to share.

## License

By contributing, you agree your contributions are licensed under [Apache-2.0](LICENSE).
