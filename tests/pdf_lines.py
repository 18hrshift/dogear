"""Hand-placed PDF lines for unit tests that don't need a real PDF.

Positions are in PDF points from the page's top-left corner, as pdfplumber reports them:
11 pt body text on a 14 pt line pitch, starting at the 72 pt margin.
"""

from __future__ import annotations

from dogear.config import Config
from dogear.extract.pdf_text import Layout, Line

BODY = 11.0
PITCH = 14.0


def ln(
    text: str,
    top: float,
    *,
    x0: float = 72.0,
    size: float = BODY,
    x1: float = 0,
    **fields,
) -> Line:
    """A line whose box is as tall as its font size, like pdfplumber reports."""
    return Line(
        text=text,
        top=top,
        bottom=top + size,
        x0=x0,
        x1=x1 or x0 + 5.0 * len(text),
        size=size,
        chars=len(text.replace(" ", "")),
        **fields,
    )


def body_lines(start: float, count: int, prefix: str = "body") -> list[Line]:
    return [ln(f"{prefix} line {i} of the page", start + i * PITCH, x1=540) for i in range(count)]


def layout_for(config: Config, **overrides) -> Layout:
    """The layout of a book of BODY-size text, with ratios from `config`."""
    pdf = config["pdf"]
    fields = dict(
        body_size=BODY,
        heading_size=BODY * pdf["heading_size_ratio"],
        line_pitch=PITCH,
        gap_ratio=pdf["paragraph_gap_ratio"],
        indent=BODY * pdf["paragraph_indent_ratio"],
    )
    return Layout(**{**fields, **overrides})
