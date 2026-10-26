"""Package rendered chapters as finished audiobooks, using ffmpeg.

One packager per format (`m4b`). It normalizes loudness itself (`loudness`), so the
caller passes the renderer's raw WAV files:

    from dogear.output import ChapterAudio, build_m4b
"""

from dogear.output.chapter import ChapterAudio
from dogear.output.ffmpeg import probe_duration
from dogear.output.m4b import build_m4b

__all__ = ["ChapterAudio", "build_m4b", "probe_duration"]
