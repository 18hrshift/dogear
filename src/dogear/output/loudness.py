"""Loudness normalization, so every chapter plays at the same level.

Two ffmpeg passes per chapter. The first measures integrated loudness and true peak with
the EBU R128 meter (`ebur128`). The second turns the whole chapter up or down by one
fixed amount (`volume`), which keeps the voice's own dynamics: nothing pumps. If that
gain would push true peaks over the ceiling, a lookahead limiter (`alimiter`, run at four
times the sample rate so it also sees peaks between samples) shaves them off, by at most
`max_limiting_db`. Past that, the gain is lowered instead and a warning says the chapter
ends up quieter than the target.

ffmpeg's `loudnorm` filter isn't used: in linear mode it silently falls back to dynamic
(pumping) normalization whenever peaks would cross its ceiling, and its measuring pass
is several times slower than `ebur128`.
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass
from pathlib import Path

from dogear.config import Config
from dogear.errors import ConfigError, ToolFailedError
from dogear.output.ffmpeg import probe_sample_rate
from dogear.tools import find_tool, run_tool

log = logging.getLogger(__name__)

# alimiter's `limit` runs from 0.0625 to 1 (linear), which is about -24 to 0 dB.
_LOWEST_CEILING_DB = -24.0


@dataclass(frozen=True)
class LoudnessSettings:
    target_lufs: float
    ceiling_dbtp: float
    max_limiting_db: float
    silence_threshold_lufs: float

    @classmethod
    def from_config(cls, config: Config) -> LoudnessSettings:
        audio = config["audio"]
        settings = cls(
            target_lufs=float(audio["loudness_target_lufs"]),
            ceiling_dbtp=float(audio["true_peak_ceiling_dbtp"]),
            max_limiting_db=float(audio["max_limiting_db"]),
            silence_threshold_lufs=float(audio["silence_threshold_lufs"]),
        )
        settings._check()
        return settings

    def _check(self) -> None:
        if not _LOWEST_CEILING_DB <= self.ceiling_dbtp <= 0:
            raise ConfigError(
                f"audio.true_peak_ceiling_dbtp is {self.ceiling_dbtp}, outside -24 to 0.",
                hint="Set it to a value from -24 to 0, such as -3.",
            )
        if self.target_lufs >= self.ceiling_dbtp:
            raise ConfigError(
                f"audio.loudness_target_lufs ({self.target_lufs}) must be lower than "
                f"audio.true_peak_ceiling_dbtp ({self.ceiling_dbtp}).",
                hint="Speech needs room for peaks: a target about 15 below the ceiling works.",
            )
        if self.silence_threshold_lufs >= self.target_lufs:
            raise ConfigError(
                f"audio.silence_threshold_lufs ({self.silence_threshold_lufs}) must be lower "
                f"than audio.loudness_target_lufs ({self.target_lufs}).",
                hint="A value around -50 treats only near-silence as silent.",
            )
        if self.max_limiting_db < 0:
            raise ConfigError(
                f"audio.max_limiting_db is {self.max_limiting_db}, but it can't be negative.",
                hint="Use 0 to never limit peaks, or a few dB such as 6.",
            )


@dataclass(frozen=True)
class Loudness:
    """What the meter found. -70 LUFS means nothing was loud or long enough to measure."""

    integrated_lufs: float
    true_peak_dbtp: float  # -inf for digital silence


@dataclass(frozen=True)
class GainPlan:
    gain_db: float
    limit: bool  # run the peak limiter after the gain
    silent: bool = False  # too quiet or too short to measure, so left as it is
    shortfall_db: float = 0.0  # how far under the target the peaks forced it to stay


def plan_gain(measured: Loudness, settings: LoudnessSettings) -> GainPlan:
    """The one gain that brings a chapter to the target, within the peak rules."""
    peak = measured.true_peak_dbtp
    if measured.integrated_lufs < settings.silence_threshold_lufs:
        return GainPlan(0.0, limit=peak > settings.ceiling_dbtp, silent=True)
    wanted = settings.target_lufs - measured.integrated_lufs
    # The most gain allowed: peaks may land at most max_limiting_db over the ceiling.
    allowed = settings.ceiling_dbtp + settings.max_limiting_db - peak
    gain = min(wanted, allowed)
    return GainPlan(gain, limit=peak + gain > settings.ceiling_dbtp, shortfall_db=wanted - gain)


def filter_chain(plan: GainPlan, settings: LoudnessSettings, sample_rate: int) -> str:
    """The ffmpeg audio filter that carries out a plan, ending at the input's sample rate."""
    chain = f"volume={plan.gain_db:.2f}dB"
    if plan.limit:
        limit = 10 ** (settings.ceiling_dbtp / 20)
        # level=false: don't raise the output back up. latency=true: keep timing and length.
        chain += (
            f",aresample={4 * sample_rate}"
            f",alimiter=limit={limit:.5f}:attack=5:release=50:level=false:latency=true"
            f",aresample={sample_rate}"
        )
    return chain


def normalize_filter(path: Path, label: str, settings: LoudnessSettings, config: Config) -> str:
    """Measure one chapter, log what will happen to it, and return the filter to apply."""
    measured = measure_loudness(path, config)
    plan = plan_gain(measured, settings)
    _log_plan(label, measured, plan, settings)
    return filter_chain(plan, settings, probe_sample_rate(path, config))


def measure_loudness(path: Path, config: Config) -> Loudness:
    ffmpeg = find_tool("ffmpeg", config)
    # framelog=verbose logs the meter's per-frame lines below the default log level, so
    # stderr holds little more than the final summary.
    result = run_tool(
        [ffmpeg, "-hide_banner", "-nostdin", "-nostats", "-i", str(path), "-map", "0:a:0"]
        + ["-af", "ebur128=peak=true:framelog=verbose", "-f", "null", "-"]
    )
    return parse_ebur128_summary(result.stderr, path.name)


_INTEGRATED = re.compile(r"^\s*I:\s*(\S+) LUFS", re.MULTILINE)
_TRUE_PEAK = re.compile(r"^\s*Peak:\s*(\S+) dBFS", re.MULTILINE)


def parse_ebur128_summary(stderr: str, name: str) -> Loudness:
    """Read integrated loudness and true peak from the summary ebur128 logs at the end."""
    start = stderr.rfind("Summary:")
    summary = stderr[start:] if start >= 0 else ""
    integrated = _number(_INTEGRATED.search(summary))
    peak = _number(_TRUE_PEAK.search(summary))
    if integrated is None or peak is None:
        raise ToolFailedError(f"ffmpeg didn't report the loudness of {name}.")
    return Loudness(integrated, peak)


def _number(match: re.Match[str] | None) -> float | None:
    # A level in dB: a finite number, or "-inf" for digital silence.
    if match is None:
        return None
    try:
        value = float(match.group(1))
    except ValueError:
        return None
    return None if math.isnan(value) or value == math.inf else value


def _log_plan(label: str, measured: Loudness, plan: GainPlan, settings: LoudnessSettings) -> None:
    if plan.silent:
        log.warning("%s is silent or too short to measure, so its level is left as it is.", label)
    elif plan.shortfall_db >= 0.05:
        log.warning(
            "%s has peaks too high to reach %.1f LUFS without heavy limiting. "
            "It ends up %.1f dB quieter than the other chapters.",
            label,
            settings.target_lufs,
            plan.shortfall_db,
        )
    else:
        log.info(
            "%s measured %.1f LUFS and was adjusted by %+.1f dB%s.",
            label,
            measured.integrated_lufs,
            plan.gain_db,
            ", with peaks limited" if plan.limit else "",
        )
