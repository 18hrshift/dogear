"""Language tags from a book, checked before they go into a talking book's markup.

A book's language tags come from the book file, so they can be anything: "en_US",
"English", "und". Reading apps and validators expect a well-formed BCP 47 tag whose
first part is a real ISO 639 language code. This keeps the tags that meet that (fixing
"en_US" to "en-US") and turns the rest into None, so the caller falls back to the
language around it.
"""

from __future__ import annotations

import re

from dogear.output.languages import iso639_2

# A language code, then subtags (region, script, variant, private use) of 1 to 8 letters
# or digits each.
_WELL_FORMED = re.compile(r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{1,8})*")


def language_tag(tag: str | None) -> str | None:
    """`tag` as a well-formed BCP 47 tag for a real language, or None."""
    if not tag:
        return None
    cleaned = tag.strip().replace("_", "-")
    if not _WELL_FORMED.fullmatch(cleaned) or iso639_2(cleaned) is None:
        return None
    return cleaned
