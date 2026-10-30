"""One section's Media Overlay: a SMIL 3 file pairing each element of its text with the
stretch of its audio that speaks it.

Times are whole milliseconds. Every clip boundary is rounded the same way, so a clip
ends exactly where the next begins, as they do in the audio, and the durations in the
package add up exactly.
"""

from __future__ import annotations

from dataclasses import dataclass

from lxml import etree

from dogear.output.epub3_xhtml import EPUB_NS, EPUB_TYPE
from dogear.readalong.model import SectionText

SMIL_NS = "http://www.w3.org/ns/SMIL"


@dataclass(frozen=True)
class Overlay:
    smil: etree._Element
    milliseconds: int  # of audio its clips play, end to end


def media_overlay(
    section: SectionText, text_href: str, audio_href: str, text_ids: set[str]
) -> Overlay:
    """The SMIL for `section`, whose text is at `text_href` with the ids `text_ids` and
    whose audio is at `audio_href`, both relative to the SMIL file."""
    smil = etree.Element(_tag("smil"), nsmap={None: SMIL_NS, "epub": EPUB_NS}, version="3.0")
    body = etree.SubElement(smil, _tag("body"))
    seq = etree.SubElement(body, _tag("seq"), {f"{{{EPUB_NS}}}textref": text_href})
    played = 0
    for sync in section.syncs:
        if sync.target not in text_ids:
            raise ValueError(
                f"Sync {sync.id} of section {section.number} points at {sync.target}, "
                "which isn't in the section's text."
            )
        if sync.clip.end <= sync.clip.begin:
            raise ValueError(f"Sync {sync.id} of section {section.number} has an empty clip.")
        begin, end = milliseconds(sync.clip.begin), milliseconds(sync.clip.end)
        if end == begin:
            continue  # under a millisecond of sound: nothing a player could play
        par = etree.SubElement(seq, _tag("par"), {"id": sync.id})
        if sync.page:  # an announced page number, which players may skip
            par.set(EPUB_TYPE, "pagebreak")
        etree.SubElement(par, _tag("text"), {"src": f"{text_href}#{sync.target}"})
        clip = {"src": audio_href, "clipBegin": clock(begin), "clipEnd": clock(end)}
        etree.SubElement(par, _tag("audio"), clip)
        played += end - begin
    if not played:
        raise ValueError(f"Section {section.number} has no audio in step with its text.")
    return Overlay(smil, played)


def milliseconds(seconds: float) -> int:
    return round(seconds * 1000)


def clock(ms: int) -> str:
    """A SMIL clock value, hours:minutes:seconds.milliseconds, such as 0:01:02.345."""
    hours, rest = divmod(ms, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    seconds, ms = divmod(rest, 1000)
    return f"{hours}:{minutes:02d}:{seconds:02d}.{ms:03d}"


def serialize(smil: etree._Element) -> bytes:
    return etree.tostring(smil, xml_declaration=True, encoding="utf-8", pretty_print=True)


def _tag(name: str) -> str:
    return f"{{{SMIL_NS}}}{name}"
