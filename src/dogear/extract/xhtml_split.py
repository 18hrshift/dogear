"""Cut an XHTML <body> into consecutive stretches that start at given elements.

A table of contents can point into the middle of a file (`book.xhtml#chapter-3`), so one
file may hold several chapters. `split_body` cuts the body just before each start element,
wherever it sits: a chapter that begins mid-paragraph splits that paragraph in two.

Each stretch is returned as a body element of its own, so it can be read like a whole
document. The elements that enclose a start element are copied as empty shells (same tag
and attributes) to hold the stretch, so language, epub:type, and list or table structure
carry over. A shell never keeps its `id`: the original element stays in the earlier
stretch, and a duplicate id would repeat a page marker or a note.

Nodes are moved, not copied, so memory and time stay proportional to the file's size
however many stretches it has.
"""

from __future__ import annotations

from collections.abc import Sequence

from lxml import etree


def split_body(body: etree._Element, starts: Sequence[etree._Element]) -> list[etree._Element]:
    """`body` cut before each of `starts`: the stretch before the first, then one per start.

    `starts` must be distinct descendants of `body`, in document order. `body` itself is
    changed: it ends up holding the first stretch and is returned as the first item.
    """
    stretches = [_cut(body, start) for start in reversed(starts)]
    return [body, *reversed(stretches)]


def _cut(body: etree._Element, start: etree._Element) -> etree._Element:
    """Move `start` and everything after it out of `body`; return the new body holding it."""
    node, piece = start, None  # `piece` stands in for `node` in the new tree
    while node is not body:
        parent = node.getparent()
        if parent is None:
            raise ValueError("start element is not inside body")
        shell = _shell(parent)
        if piece is None:
            following = [node, *node.itersiblings()]
        else:
            shell.append(piece)
            piece.tail, node.tail = node.tail, None
            following = list(node.itersiblings())
        for sibling in following:
            shell.append(sibling)  # moves it, with the text that follows it
        node, piece = parent, shell
    if piece is None:
        raise ValueError("start element is body itself")
    return piece


def _shell(el: etree._Element) -> etree._Element:
    shell = etree.Element(el.tag, nsmap=el.nsmap)
    for name, value in el.attrib.items():
        if name != "id":
            shell.set(name, value)
    return shell
