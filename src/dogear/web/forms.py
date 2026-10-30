"""Reading the page's small forms (everything but the upload), with a bound on their size."""

from __future__ import annotations

from urllib.parse import parse_qsl

from starlette.requests import ClientDisconnect, Request

MAX_FORM_BYTES = 256 * 1024  # a choose form for MAX_SECTIONS sections is about 40 KB
MAX_FIELDS = 10_000


class FormTooBig(Exception):
    pass


async def read_form(
    request: Request, max_bytes: int = MAX_FORM_BYTES, max_fields: int = MAX_FIELDS
) -> list[tuple[str, str]]:
    """The form's fields, in order. Raises FormTooBig past `max_bytes` or `max_fields`:
    MAX_FORM_BYTES and MAX_FIELDS, unless a form that can hold more says how much."""
    body = bytearray()
    try:
        async for chunk in request.stream():
            body += chunk
            if len(body) > max_bytes:
                raise FormTooBig
    except ClientDisconnect:
        return []
    try:
        return parse_qsl(
            body.decode("utf-8", errors="replace"),
            keep_blank_values=True,
            max_num_fields=max_fields,
        )
    except ValueError:
        raise FormTooBig from None


def first(fields: list[tuple[str, str]], name: str) -> str:
    return next((value for key, value in fields if key == name), "")


def every(fields: list[tuple[str, str]], name: str) -> list[str]:
    return [value for key, value in fields if key == name]
