"""Times in a DAISY 2.02 book: clip boundaries in whole milliseconds, and how each is written.

The spec asks for clips in millisecond resolution. Each boundary between two clips is
rounded to a millisecond once, and every duration and running total in the book is added
up from those whole milliseconds, never from durations rounded on their own. So the times
the NCC and SMIL files declare are exactly what a player or validator gets by adding up
the clips, and stay within a millisecond per section of the audio's real length.
"""

from __future__ import annotations

from dogear.readalong.model import SectionText


def clip_bounds(section: SectionText) -> tuple[int, ...]:
    """Where each of the section's clips begins, then where the last one ends, in ms.

    One more boundary than there are syncs, strictly increasing: a clip shorter than
    a millisecond is stretched to one, because players can't play an empty clip.
    """
    syncs = section.syncs
    if not syncs:
        raise ValueError(f"Section {section.number} has no audio to tie its text to.")
    for before, after in zip(syncs, syncs[1:], strict=False):
        if before.clip.end != after.clip.begin:
            raise ValueError(
                f"Section {section.number}: clip {before.id} ends at {before.clip.end}s "
                f"but {after.id} begins at {after.clip.begin}s; clips must run back to back."
            )
    seconds = [syncs[0].clip.begin, *(s.clip.end for s in syncs)]
    bounds = [round(s * 1000) for s in seconds]
    for i in range(1, len(bounds)):
        bounds[i] = max(bounds[i], bounds[i - 1] + 1)
    return tuple(bounds)


def npt(ms: int) -> str:
    """A clip-begin or clip-end value: 'npt=72.200s'."""
    return f"npt={timecount(ms)}"


def timecount(ms: int) -> str:
    """Seconds with three decimals, as a SMIL timecount: '158.485s'."""
    _check(ms)
    return f"{ms // 1000}.{ms % 1000:03d}s"


def clock(ms: int) -> str:
    """A SMIL full clock value with milliseconds: '01:02:38.485'."""
    _check(ms)
    seconds, millis = divmod(ms, 1000)
    return f"{_hms(seconds)}.{millis:03d}"


def whole_seconds(ms: int) -> str:
    """'hh:mm:ss' rounded to the nearest second (half up), as ncc:totalTime is written."""
    _check(ms)
    return _hms((ms + 500) // 1000)


def _hms(seconds: int) -> str:
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _check(ms: int) -> None:
    if ms < 0:
        raise ValueError(f"a time can't be negative: {ms} ms")
