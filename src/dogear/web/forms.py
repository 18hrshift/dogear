"""Reading the page's small forms (everything but the upload), with a bound on their size."""

from __future__ import annotations

from urllib.parse import parse_qsl

from starlette.requests import ClientDisconnect, Request

MAX_FORM_BYTES = 256 * 1024  # a choose form for MAX_SECTIONS sections is about 40 KB
MAX_FIELDS = 10_000


class FormTooBig(Exception):
    pass


async def read_form(request: Request) -> list[tuple[str, str]]:
    """The form's fields, in order. Raises FormTooBig past MAX_FORM_BYTES or MAX_FIELDS."""
    body = bytearray()
    try:
        async for chunk in request.stream():
            body += chunk
            if len(body) > MAX_FORM_BYTES:
                raise FormTooBig
    except ClientDisconnect:
        return []
    try:
        return parse_qsl(
            body.decode("utf-8", errors="replace"),
            keep_blank_values=True,
            max_num_fields=MAX_FIELDS,
        )
    except ValueError:
        raise FormTooBig from None


def first(fields: list[tuple[str, str]], name: str) -> str:
    return next((value for key, value in fields if key == name), "")


def every(fields: list[tuple[str, str]], name: str) -> list[str]:
    return [value for key, value in fields if key == name]
