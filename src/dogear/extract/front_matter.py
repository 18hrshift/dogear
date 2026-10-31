"""Read the YAML front matter at the top of a Markdown file: its title, authors, and language.

Front matter is the block between a first line of `---` and the next `---` (or `...`):

    ---
    title: The Sample Book
    author: Ada Writer        # or authors: [Ada Writer, Bo Coauthor], or a list of lines
    lang: en-GB               # or language: en-GB
    ---

It is parsed with PyYAML's BaseLoader, which makes only text, lists, and mappings: no tag
can build any other object, and every value stays text as written, so `lang: no`
(Norwegian) is "no", not false. Other keys are for other programs and are ignored.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import yaml

from dogear.errors import ExtractionError

log = logging.getLogger(__name__)

TITLE_KEYS = ("title",)
AUTHOR_KEYS = ("author", "authors")
LANGUAGE_KEYS = ("lang", "language")


class NotFrontMatter(Exception):
    """The block parsed, but as something other than key: value pairs, so it isn't front
    matter: a Markdown file can open with a `---` rule, too."""


@dataclass(frozen=True)
class FrontMatter:
    title: str | None = None
    authors: tuple[str, ...] = ()
    language: str | None = None


def read_front_matter(source: str, what: str) -> FrontMatter:
    """The metadata in `source`, the text between the `---` lines of the file `what`."""
    try:
        data = yaml.load(source, Loader=yaml.BaseLoader)  # text, lists, and mappings only
    except yaml.YAMLError as e:
        raise ExtractionError(
            f"The front matter at the top of {what} isn't valid YAML ({_problem(e)}).",
            hint=(
                "Fix the lines between the first two --- lines. A value with a colon in it "
                'needs quotes, such as title: "Dogear: A Story".'
            ),
        ) from None
    if data is None:
        return FrontMatter()
    if not isinstance(data, dict):
        raise NotFrontMatter
    fields = {str(k).strip().casefold(): v for k, v in data.items()}
    return FrontMatter(
        title=_text(fields, TITLE_KEYS, what),
        authors=_names(fields, AUTHOR_KEYS, what),
        language=_text(fields, LANGUAGE_KEYS, what),
    )


def _text(fields: dict[str, Any], keys: tuple[str, ...], what: str) -> str | None:
    for key in keys:
        value = fields.get(key)
        if isinstance(value, str) and value.strip():
            return " ".join(value.split())
        if value is not None and not isinstance(value, str):
            _ignored(key, what)
    return None


def _names(fields: dict[str, Any], keys: tuple[str, ...], what: str) -> tuple[str, ...]:
    for key in keys:
        value = fields.get(key)
        if isinstance(value, str):
            value = [value]
        if isinstance(value, list) and all(isinstance(v, str) for v in value):
            names = [" ".join(v.split()) for v in value]
            if any(names):
                return tuple(dict.fromkeys(n for n in names if n))
        elif value is not None:
            _ignored(key, what)
    return ()


def _ignored(key: str, what: str) -> None:
    log.warning(
        "Ignored %r in the front matter of %s: Dogear reads it only as text or a list of texts.",
        key,
        what,
    )


def _problem(e: yaml.YAMLError) -> str:
    mark = getattr(e, "problem_mark", None)
    problem = getattr(e, "problem", None) or "it can't be read"
    if mark is None:
        return problem
    return f"{problem}, on line {mark.line + 2}"  # +1 for counting from 1, +1 for the ---
