"""Deterministic technical QA for assembled SynthPost video files.

The checks in this module deliberately stop at machine-verifiable properties.
Black frames and sustained silence are reported for human review, while broken
containers, missing streams, decode errors, profile mismatches, A/V skew, and
unsafe loudness fail the gate.
"""

from __future__ import annotations

import json
import math
import os
import re
import subprocess
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from pipeline import config
from pipeline.models import StrictModel, now_iso
from pipeline.storage import project_relative, resolve_project_path


QA_CONTRACT_VERSION = "synthpost.final_video_qa.v1"
AV_DURATION_TOLERANCE_SECONDS = 0.5
MIN_INTEGRATED_LOUDNESS_LUFS = -18.0
MAX_INTEGRATED_LOUDNESS_LUFS = -14.0
MAX_TRUE_PEAK_DBFS = -1.0
SILENCE_WARNING_SECONDS = 5.0
BLACK_WARNING_SECONDS = 2.0
SUBPROCESS_TIMEOUT_SECONDS = 30 * 60

CommandRunner = Callable[..., subprocess.CompletedProcess[str]]


class VideoQAFinding(StrictModel):
    """One stable, UI-safe result from the final-video gate."""

    code: str
    severity: Literal["warning", "error"]
    message: str
    measured: float | int | str | None = None
    expected: float | int | str | None = None


class FinalVideoQAReport(StrictModel):
    """Persisted result of one final-video QA evaluation."""

    contract_version: Literal["synthpost.final_video_qa.v1"] = QA_CONTRACT_VERSION
    status: Literal["passed", "failed"]
    passed: bool
    input_path: str
    report_path: str
    checked_at: str = Field(default_factory=now_iso)
    expected_width: int | None = None
    expected_height: int | None = None
    expected_fps: float | None = None
    probe: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, float | int | str | None] = Field(default_factory=dict)
    findings: list[VideoQAFinding] = Field(default_factory=list)


class FinalVideoQAError(ValueError):
    """Raised after a failed report has safely been persisted."""

    def __init__(self, report: FinalVideoQAReport):
        self.report = report
        codes = ", ".join(
            finding.code
            for finding in report.findings
            if finding.severity == "error"
        )
        super().__init__(f"Final video QA failed: {codes or 'unknown_error'}")


def _runner(value: CommandRunner | None) -> CommandRunner:
    return value or subprocess.run


def _ffmpeg_binary() -> str:
    return config.ffmpeg_binary()


def _ffprobe_binary() -> str:
    """Resolve ffprobe beside a configured absolute FFmpeg when applicable."""

    ffmpeg = Path(_ffmpeg_binary())
    if ffmpeg.parent != Path("."):
        return str(ffmpeg.with_name("ffprobe"))
    return "ffprobe"


def _run(
    command: list[str],
    *,
    runner: CommandRunner | None,
    timeout: float = SUBPROCESS_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[str]:
    return _runner(runner)(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _safe_detail(result: subprocess.CompletedProcess[str]) -> str:
    raw = (result.stderr or result.stdout or "").strip()
    if not raw:
        return f"process exited with code {result.returncode}"
    return raw.splitlines()[-1][-500:]


def _number(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _frame_rate(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return _number(value)
    text = str(value or "").strip()
    if not text:
        return None
    if "/" not in text:
        return _number(text)
    numerator, denominator = text.split("/", 1)
    top = _number(numerator)
    bottom = _number(denominator)
    if top is None or bottom in (None, 0):
        return None
    return top / bottom


def _finding(
    code: str,
    severity: Literal["warning", "error"],
    message: str,
    *,
    measured: float | int | str | None = None,
    expected: float | int | str | None = None,
) -> VideoQAFinding:
    return VideoQAFinding(
        code=code,
        severity=severity,
        message=message,
        measured=measured,
        expected=expected,
    )


def _strict_probe(
    path: Path, *, runner: CommandRunner | None
) -> tuple[dict[str, Any], VideoQAFinding | None]:
    command = [
        _ffprobe_binary(),
        "-v",
        "error",
        "-show_entries",
        (
            "format=duration,size,format_name:"
            "stream=index,codec_type,codec_name,width,height,pix_fmt,"
            "avg_frame_rate,sample_rate,channels,duration"
        ),
        "-of",
        "json",
        str(path),
    ]
    try:
        result = _run(command, runner=runner, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {}, _finding(
            "probe_failed", "error", f"ffprobe could not inspect the video: {exc}"
        )
    if result.returncode != 0:
        return {}, _finding(
            "probe_failed",
            "error",
            f"ffprobe rejected the video: {_safe_detail(result)}",
        )
    try:
        raw = json.loads(result.stdout)
    except (TypeError, json.JSONDecodeError):
        return {}, _finding(
            "probe_invalid_json", "error", "ffprobe returned invalid JSON"
        )
    if not isinstance(raw, dict):
        return {}, _finding(
            "probe_invalid_json", "error", "ffprobe did not return a JSON object"
        )
    return raw, None


def _decode_check(
    path: Path, *, runner: CommandRunner | None
) -> VideoQAFinding | None:
    command = [
        _ffmpeg_binary(),
        "-hide_banner",
        "-nostats",
        "-v",
        "error",
        "-xerror",
        "-i",
        str(path),
        "-map",
        "0:v:0",
        "-map",
        "0:a:0",
        "-f",
        "null",
        "-",
    ]
    try:
        result = _run(command, runner=runner)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return _finding(
            "decode_failed", "error", f"FFmpeg could not decode the video: {exc}"
        )
    if result.returncode != 0:
        return _finding(
            "decode_failed",
            "error",
            f"FFmpeg found a decode error: {_safe_detail(result)}",
        )
    return None


_LOUDNESS_PATTERN = re.compile(
    r"Integrated loudness:\s*I:\s*(?P<lufs>-?inf|nan|-?\d+(?:\.\d+)?)\s*LUFS",
    flags=re.IGNORECASE | re.DOTALL,
)
_TRUE_PEAK_PATTERN = re.compile(
    r"True peak:\s*Peak:\s*(?P<peak>-?inf|nan|-?\d+(?:\.\d+)?)\s*dBFS",
    flags=re.IGNORECASE | re.DOTALL,
)


def _loudness_check(
    path: Path,
    *,
    runner: CommandRunner | None,
) -> tuple[dict[str, float | None], list[VideoQAFinding]]:
    command = [
        _ffmpeg_binary(),
        "-hide_banner",
        "-nostats",
        "-i",
        str(path),
        "-map",
        "0:a:0",
        "-af",
        "ebur128=peak=true",
        "-f",
        "null",
        "-",
    ]
    try:
        result = _run(command, runner=runner)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {}, [
            _finding(
                "loudness_analysis_failed",
                "error",
                f"FFmpeg could not measure loudness: {exc}",
            )
        ]
    if result.returncode != 0:
        return {}, [
            _finding(
                "loudness_analysis_failed",
                "error",
                f"FFmpeg loudness analysis failed: {_safe_detail(result)}",
            )
        ]

    output = result.stderr or result.stdout or ""
    summary = output.rsplit("Summary:", 1)[-1]
    loudness_match = _LOUDNESS_PATTERN.search(summary)
    peak_match = _TRUE_PEAK_PATTERN.search(summary)
    integrated = _number(loudness_match.group("lufs")) if loudness_match else None
    true_peak = _number(peak_match.group("peak")) if peak_match else None
    metrics: dict[str, float | None] = {
        "integrated_loudness_lufs": integrated,
        "true_peak_dbfs": true_peak,
    }
    findings: list[VideoQAFinding] = []
    if integrated is None:
        findings.append(
            _finding(
                "loudness_unmeasurable",
                "error",
                "Integrated loudness could not be measured",
            )
        )
    elif not (
        MIN_INTEGRATED_LOUDNESS_LUFS
        <= integrated
        <= MAX_INTEGRATED_LOUDNESS_LUFS
    ):
        findings.append(
            _finding(
                "loudness_out_of_range",
                "error",
                "Integrated loudness is outside the production window",
                measured=round(integrated, 2),
                expected=(
                    f"{MIN_INTEGRATED_LOUDNESS_LUFS:.1f} to "
                    f"{MAX_INTEGRATED_LOUDNESS_LUFS:.1f} LUFS"
                ),
            )
        )
    if true_peak is None:
        findings.append(
            _finding(
                "true_peak_unmeasurable",
                "error",
                "Audio true peak could not be measured",
            )
        )
    elif true_peak > MAX_TRUE_PEAK_DBFS:
        findings.append(
            _finding(
                "true_peak_too_high",
                "error",
                "Audio true peak exceeds the production ceiling",
                measured=round(true_peak, 2),
                expected=f"<= {MAX_TRUE_PEAK_DBFS:.1f} dBFS",
            )
        )
    return metrics, findings


def _content_check(
    path: Path,
    *,
    runner: CommandRunner | None,
    kind: Literal["silence", "black"],
) -> tuple[float | None, VideoQAFinding | None]:
    if kind == "silence":
        filter_arguments = ["-af", "silencedetect=noise=-50dB:d=5"]
        duration_pattern = re.compile(r"silence_duration:\s*(\d+(?:\.\d+)?)")
        failure_code = "silence_analysis_failed"
        warning_code = "sustained_silence"
        threshold = SILENCE_WARNING_SECONDS
        label = "silence"
        stream_arguments = ["-map", "0:a:0"]
    else:
        filter_arguments = ["-vf", "blackdetect=d=2:pix_th=0.10"]
        duration_pattern = re.compile(r"black_duration:\s*(\d+(?:\.\d+)?)")
        failure_code = "black_analysis_failed"
        warning_code = "sustained_black_frames"
        threshold = BLACK_WARNING_SECONDS
        label = "black frames"
        stream_arguments = ["-an"]
    command = [
        _ffmpeg_binary(),
        "-hide_banner",
        "-nostats",
        "-i",
        str(path),
        *stream_arguments,
        *filter_arguments,
        "-f",
        "null",
        "-",
    ]
    try:
        result = _run(command, runner=runner)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, _finding(
            failure_code,
            "warning",
            f"FFmpeg could not analyze {label}: {exc}",
        )
    if result.returncode != 0:
        return None, _finding(
            failure_code,
            "warning",
            f"FFmpeg {label} analysis failed: {_safe_detail(result)}",
        )
    output = result.stderr or result.stdout or ""
    durations = [float(value) for value in duration_pattern.findall(output)]
    longest = max(durations) if durations else 0.0
    if longest >= threshold:
        return longest, _finding(
            warning_code,
            "warning",
            f"The video contains a sustained interval of {label}",
            measured=round(longest, 3),
            expected=f"< {threshold:.1f} seconds",
        )
    return longest, None


def _write_report(path: Path, report: FinalVideoQAReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(
                report.model_dump(mode="json"),
                handle,
                indent=2,
                ensure_ascii=True,
            )
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def run_final_video_qa(
    path: str | Path,
    report_path: str | Path,
    expected_width: int | None = None,
    expected_height: int | None = None,
    expected_fps: float | None = None,
    *,
    runner: CommandRunner | None = None,
) -> FinalVideoQAReport:
    """Validate one final MP4, persist its report, and return or raise.

    ``runner`` is an injectable ``subprocess.run``-compatible callable for unit
    tests. A failing report is always written before ``FinalVideoQAError`` is
    raised, so unattended runs retain actionable evidence.
    """

    video_path = resolve_project_path(path)
    qa_path = resolve_project_path(report_path)
    findings: list[VideoQAFinding] = []
    probe: dict[str, Any] = {}
    metrics: dict[str, float | int | str | None] = {}

    if not video_path.exists() or not video_path.is_file():
        findings.append(
            _finding("file_missing", "error", "Final video file does not exist")
        )
    elif video_path.stat().st_size <= 0:
        findings.append(_finding("file_empty", "error", "Final video file is empty"))
    else:
        metrics["size_bytes"] = video_path.stat().st_size
        probe, probe_finding = _strict_probe(video_path, runner=runner)
        if probe_finding:
            findings.append(probe_finding)

    if probe:
        raw_streams = probe.get("streams")
        streams = raw_streams if isinstance(raw_streams, list) else []
        video_streams = [
            stream
            for stream in streams
            if isinstance(stream, dict) and stream.get("codec_type") == "video"
        ]
        audio_streams = [
            stream
            for stream in streams
            if isinstance(stream, dict) and stream.get("codec_type") == "audio"
        ]
        metrics["video_stream_count"] = len(video_streams)
        metrics["audio_stream_count"] = len(audio_streams)
        if not video_streams:
            findings.append(
                _finding(
                    "video_stream_missing", "error", "Final video has no video stream"
                )
            )
        if not audio_streams:
            findings.append(
                _finding(
                    "audio_stream_missing", "error", "Final video has no audio stream"
                )
            )
        if len(video_streams) > 1:
            findings.append(
                _finding(
                    "multiple_video_streams",
                    "warning",
                    "Final video contains multiple video streams",
                    measured=len(video_streams),
                    expected=1,
                )
            )
        if len(audio_streams) > 1:
            findings.append(
                _finding(
                    "multiple_audio_streams",
                    "warning",
                    "Final video contains multiple audio streams",
                    measured=len(audio_streams),
                    expected=1,
                )
            )

        format_data = probe.get("format")
        media_format = format_data if isinstance(format_data, dict) else {}
        duration = _number(media_format.get("duration"))
        metrics["duration_seconds"] = duration
        if duration is None or duration <= 0:
            findings.append(
                _finding(
                    "duration_invalid",
                    "error",
                    "Final video duration is missing or non-positive",
                    measured=duration,
                    expected="> 0 seconds",
                )
            )

        if video_streams:
            video = video_streams[0]
            width = int(video.get("width") or 0)
            height = int(video.get("height") or 0)
            fps = _frame_rate(video.get("avg_frame_rate"))
            video_duration = _number(video.get("duration"))
            metrics.update(
                {
                    "width": width,
                    "height": height,
                    "fps": round(fps, 6) if fps is not None else None,
                    "video_duration_seconds": video_duration,
                    "video_codec": str(video.get("codec_name") or ""),
                    "pixel_format": str(video.get("pix_fmt") or ""),
                }
            )
            width_mismatch = expected_width is not None and width != expected_width
            height_mismatch = (
                expected_height is not None and height != expected_height
            )
            if width_mismatch or height_mismatch:
                findings.append(
                    _finding(
                        "resolution_mismatch",
                        "error",
                        "Final video resolution does not match the render profile",
                        measured=f"{width}x{height}",
                        expected=(
                            f"{expected_width if expected_width is not None else 'any'}x"
                            f"{expected_height if expected_height is not None else 'any'}"
                        ),
                    )
                )
            if expected_fps is not None:
                tolerance = max(0.1, abs(expected_fps) * 0.005)
                if fps is None or abs(fps - expected_fps) > tolerance:
                    findings.append(
                        _finding(
                            "frame_rate_mismatch",
                            "error",
                            "Final video frame rate does not match the render profile",
                            measured=round(fps, 6) if fps is not None else None,
                            expected=expected_fps,
                        )
                    )
        else:
            video_duration = None

        if audio_streams:
            audio = audio_streams[0]
            audio_duration = _number(audio.get("duration"))
            metrics.update(
                {
                    "audio_duration_seconds": audio_duration,
                    "audio_codec": str(audio.get("codec_name") or ""),
                    "audio_sample_rate": int(audio.get("sample_rate") or 0),
                    "audio_channels": int(audio.get("channels") or 0),
                }
            )
        else:
            audio_duration = None

        if video_duration is not None and audio_duration is not None:
            skew = abs(video_duration - audio_duration)
            metrics["av_duration_skew_seconds"] = round(skew, 6)
            if skew > AV_DURATION_TOLERANCE_SECONDS:
                findings.append(
                    _finding(
                        "av_duration_skew",
                        "error",
                        "Audio and video stream durations differ too much",
                        measured=round(skew, 3),
                        expected=f"<= {AV_DURATION_TOLERANCE_SECONDS:.1f} seconds",
                    )
                )

        if video_streams and audio_streams:
            decode_finding = _decode_check(video_path, runner=runner)
            if decode_finding:
                findings.append(decode_finding)
            loudness_metrics, loudness_findings = _loudness_check(
                video_path, runner=runner
            )
            metrics.update(loudness_metrics)
            findings.extend(loudness_findings)
            longest_silence, silence_finding = _content_check(
                video_path, runner=runner, kind="silence"
            )
            metrics["longest_silence_seconds"] = longest_silence
            if silence_finding:
                findings.append(silence_finding)
            longest_black, black_finding = _content_check(
                video_path, runner=runner, kind="black"
            )
            metrics["longest_black_seconds"] = longest_black
            if black_finding:
                findings.append(black_finding)

    passed = not any(finding.severity == "error" for finding in findings)
    report = FinalVideoQAReport(
        status="passed" if passed else "failed",
        passed=passed,
        input_path=project_relative(video_path),
        report_path=project_relative(qa_path),
        expected_width=expected_width,
        expected_height=expected_height,
        expected_fps=expected_fps,
        probe=probe,
        metrics=metrics,
        findings=findings,
    )
    _write_report(qa_path, report)
    if not passed:
        raise FinalVideoQAError(report)
    return report


__all__ = [
    "FinalVideoQAError",
    "FinalVideoQAReport",
    "VideoQAFinding",
    "run_final_video_qa",
]
