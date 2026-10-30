"""A section's SMIL file in a DAISY 2.02 book: which stretch of its MP3 speaks which text.

One `par` per sync, in order, each with one `text` (the element in the section's text
document) and one `audio` clip. Clip times are written in milliseconds, and the head
declares the section's own length and the book's length before it, both added up from
those clips (see `daisy202_clock`). A narrated page number ("Page 42.") carries
`system-required="pagenumber-on"`, so players can skip page announcements.
"""

from __future__ import annotations

from pathlib import Path

from lxml import etree

from dogear.output.daisy202_clock import clock, npt, timecount
from dogear.output.daisy202_plan import BookPlan, SectionPlan
from dogear.output.xml_text import xml_safe

DOCTYPE = (
    '<!DOCTYPE smil PUBLIC "-//W3C//DTD SMIL 1.0//EN" "http://www.w3.org/TR/REC-smil/SMIL10.dtd">'
)


def smil_document(book: BookPlan, plan: SectionPlan) -> etree._Element:
    section = plan.section
    smil = etree.Element("smil")
    head = etree.SubElement(smil, "head")
    for name, content in [
        ("dc:format", "Daisy 2.02"),
        ("dc:identifier", book.identifier),
        ("dc:title", xml_safe(book.title)),
        ("ncc:generator", book.generator),
        ("ncc:totalElapsedTime", clock(plan.elapsed)),
        ("ncc:timeInThisSmil", clock(plan.duration)),
    ]:
        etree.SubElement(head, "meta", name=name, content=content)
    layout = etree.SubElement(head, "layout")
    etree.SubElement(layout, "region", id="txtView")
    seq = etree.SubElement(etree.SubElement(smil, "body"), "seq", dur=timecount(plan.duration))
    bounds = plan.bounds
    for k, sync in enumerate(section.syncs):
        par = etree.SubElement(seq, "par", endsync="last", id=sync.id)
        if sync.page:
            par.set("system-required", "pagenumber-on")
        # Each SMIL must start on a heading. The opening heading always owns the first
        # sync; this only differs from the sync's own target if the heading came out
        # silent, and then the heading is still where the section starts.
        target = plan.opening.id if k == 0 else sync.target
        etree.SubElement(par, "text", src=f"{plan.text}#{target}", id=f"{sync.id}-text")
        etree.SubElement(
            par,
            "audio",
            src=plan.audio,
            id=f"{sync.id}-audio",
            **{"clip-begin": npt(bounds[k]), "clip-end": npt(bounds[k + 1])},
        )
    return smil


def write_smil(smil: etree._Element, path: Path) -> None:
    etree.ElementTree(smil).write(
        str(path), encoding="utf-8", xml_declaration=True, doctype=DOCTYPE, pretty_print=True
    )
