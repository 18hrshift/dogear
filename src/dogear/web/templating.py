"""Rendering pages from the Jinja2 templates, with every value escaped."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from starlette.requests import Request
from starlette.responses import Response
from starlette.templating import Jinja2Templates

TEMPLATES = Path(__file__).parent / "templates"


def make_templates() -> Jinja2Templates:
    environment = Environment(
        loader=FileSystemLoader(TEMPLATES),
        autoescape=True,
        undefined=StrictUndefined,  # a missing value is a bug, not an empty string
        trim_blocks=True,
        lstrip_blocks=True,
    )
    return Jinja2Templates(env=environment)


def render(
    request: Request,
    template: str,
    title: str,
    *,
    status_code: int = 200,
    errors: dict[str, str] | None = None,
    current: str = "",
    **context: Any,
) -> Response:
    """A page. `title` comes before " - Dogear" in its <title>, after "Error: " when the
    page has `errors`. `current` names the navigation link for this page, if any."""
    templates: Jinja2Templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        template,
        {"title": title, "errors": errors or {}, "current": current, **context},
        status_code=status_code,
    )


def message(
    request: Request, status_code: int, title: str, heading: str, *paragraphs: str
) -> Response:
    """A page that only says something, such as "Page not found"."""
    return render(
        request,
        "message.html",
        title,
        status_code=status_code,
        heading=heading,
        paragraphs=paragraphs,
    )
