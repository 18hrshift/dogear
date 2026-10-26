"""Package rendered chapters as finished audiobooks, using ffmpeg.

One packager per format (`m4b`, `mp3_folder`). Both normalize loudness themselves
(`loudness`), so the caller passes the renderer's raw WAV files:

    from dogear.output import ChapterAudio, build_m4b, build_mp3_folder
"""

from dogear.output.chapter import ChapterAudio
from dogear.output.ffmpeg import probe_duration
from dogear.output.m4b import build_m4b
from dogear.output.mp3_folder import build_mp3_folder

__all__ = ["ChapterAudio", "build_m4b", "build_mp3_folder", "probe_duration"]
