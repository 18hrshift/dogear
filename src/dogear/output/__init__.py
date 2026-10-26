"""Package rendered chapters as finished audiobooks, using ffmpeg.

One packager per format (`m4b`, `mp3_folder`). Both normalize loudness themselves
(`loudness`), so the caller can pass the renderer's raw WAV files. To build several
formats, normalize once with `normalize_chapters` and pass `normalized=True` to each.

    from dogear.output import ChapterAudio, build_m4b, build_mp3_folder
"""

from dogear.output.chapter import ChapterAudio
from dogear.output.ffmpeg import probe_duration
from dogear.output.loudness import normalize_chapters
from dogear.output.m4b import build_m4b
from dogear.output.mp3_folder import build_mp3_folder

__all__ = [
    "ChapterAudio",
    "build_m4b",
    "build_mp3_folder",
    "normalize_chapters",
    "probe_duration",
]
