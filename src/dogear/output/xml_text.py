"""Text that XML can hold, for every document Dogear writes into a talking book."""

from __future__ import annotations

import re

# Control characters other than tab and line ends, unpaired surrogates, and the two
# non-characters U+FFFE and U+FFFF. A damaged book file can carry them; they hold no words.
_NOT_XML = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff￾￿]")


def xml_safe(text: str) -> str:
    """`text` without the characters XML can't hold."""
    return _NOT_XML.sub("", text)
