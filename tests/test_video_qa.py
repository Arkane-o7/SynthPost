from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from pipeline.video_qa import (
    FinalVideoQAError,
    FinalVideoQAReport,
    run_final_video_qa,
)


def probe_payload(
    *,
    width: int = 1920,
    height: int = 1080,
    fps: str = "24/1",
    duration: float = 60.0,
    video_duration: float | None = None,
    audio_duration: float | None = None,
    include_video: bool = True,
    include_audio: bool = True,
) -> dict:
    streams: list[dict] = []
    if include_video:
        streams.append(
            {
                "index": 0,
                "codec_type": "video",
                "codec_name": "h264",
                "width": width,
                "height": height,
                "pix_fmt": "yuv420p",
                "avg_frame_rate": fps,
                "duration": str(
                    duration if video_duration is None else video_duration
                ),
            }
        )
    if include_audio:
        streams.append(
            {
                "index": 1,
                "codec_type": "audio",
                "codec_name": "aac",
                "sample_rate": "48000",
                "channels": 2,
                "duration": str(
                    duration if audio_duration is None else audio_duration
                ),
            }
        )
    return {
        "streams": streams,
        "format": {
            "duration": str(duration),
            "size": "1048576",
            "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
        },
    }


def loudness_output(lufs: float = -16.2, peak: float = -2.2) -> str:
    return f"""
[Parsed_ebur128_0] Summary:

  Integrated loudness:
    I:         {lufs:.1f} LUFS
    Threshold: -26.5 LUFS

  Loudness range:
    LRA:         2.9 LU

  True peak:
    Peak:       {peak:.1f} dBFS
"""


class StubRunner:
    def __init__(
        self,
        *,
        probe: dict | None = None,
        probe_stdout: str | None = None,
        decode_returncode: int = 0,
        loudness_lufs: float = -16.2,
        true_peak: float = -2.2,
        silence_duration: float | None = None,
        black_duration: float | None = None,
    ) -> None:
        self.probe = probe if probe is not None else probe_payload()
        self.probe_stdout = probe_stdout
        self.decode_returncode = decode_returncode
        self.loudness_lufs = loudness_lufs
        self.true_peak = true_peak
        self.silence_duration = silence_duration
        self.black_duration = black_duration
        self.commands: list[list[str]] = []

    def __call__(self, command: list[str], **_kwargs):
        self.commands.append(command)
        executable = Path(command[0]).name
        if executable == "ffprobe":
            stdout = (
                self.probe_stdout
                if self.probe_stdout is not None
                else json.dumps(self.probe)
            )
            return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")
        if "-xerror" in command:
            return subprocess.CompletedProcess(
                command,
                self.decode_returncode,
                stdout="",
                stderr="invalid data while decoding" if self.decode_returncode else "",
            )
        if "ebur128=peak=true" in command:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout="",
                stderr=loudness_output(self.loudness_lufs, self.true_peak),
            )
        if "silencedetect=noise=-50dB:d=5" in command:
            stderr = ""
            if self.silence_duration is not None:
                stderr = (
                    "[silencedetect] silence_start: 10\n"
                    "[silencedetect] silence_end: 17 | "
                    f"silence_duration: {self.silence_duration}\n"
                )
            return subprocess.CompletedProcess(command, 0, stdout="", stderr=stderr)
        if "blackdetect=d=2:pix_th=0.10" in command:
            stderr = ""
            if self.black_duration is not None:
                stderr = (
                    "[blackdetect] black_start:1 black_end:4 "
                    f"black_duration:{self.black_duration}\n"
                )
            return subprocess.CompletedProcess(command, 0, stdout="", stderr=stderr)
        raise AssertionError(f"Unexpected command: {command}")


class FinalVideoQATests(unittest.TestCase):
    def test_healthy_video_passes_and_atomically_persists_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            video = root / "final.mp4"
            report_path = root / "final.qa.json"
            video.write_bytes(b"synthetic-mp4")
            report_path.write_text("stale report", encoding="utf-8")
            runner = StubRunner()

            report = run_final_video_qa(
                video,
                report_path,
                expected_width=1920,
                expected_height=1080,
                expected_fps=24,
                runner=runner,
            )

            self.assertIsInstance(report, FinalVideoQAReport)
            self.assertTrue(report.passed)
            self.assertEqual(report.status, "passed")
            self.assertEqual(report.findings, [])
            self.assertEqual(report.metrics["integrated_loudness_lufs"], -16.2)
            persisted = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(persisted["contract_version"], "synthpost.final_video_qa.v1")
            self.assertTrue(persisted["passed"])
            self.assertEqual(list(root.glob(".final.qa.json.*.tmp")), [])
            self.assertEqual(len(runner.commands), 5)

    def test_sustained_silence_and_black_frames_are_review_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            video = root / "final.mp4"
            report_path = root / "final.qa.json"
            video.write_bytes(b"synthetic-mp4")
            runner = StubRunner(silence_duration=7.25, black_duration=3.5)

            report = run_final_video_qa(video, report_path, runner=runner)

            self.assertTrue(report.passed)
            findings = {finding.code: finding for finding in report.findings}
            self.assertEqual(
                set(findings), {"sustained_silence", "sustained_black_frames"}
            )
            self.assertTrue(
                all(finding.severity == "warning" for finding in findings.values())
            )
            self.assertEqual(report.metrics["longest_silence_seconds"], 7.25)
            self.assertEqual(report.metrics["longest_black_seconds"], 3.5)

    def test_missing_audio_stream_persists_failure_before_raising(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            video = root / "final.mp4"
            report_path = root / "final.qa.json"
            video.write_bytes(b"synthetic-mp4")
            runner = StubRunner(probe=probe_payload(include_audio=False))

            with self.assertRaises(FinalVideoQAError) as raised:
                run_final_video_qa(video, report_path, runner=runner)

            self.assertTrue(report_path.is_file())
            self.assertFalse(raised.exception.report.passed)
            codes = {finding.code for finding in raised.exception.report.findings}
            self.assertEqual(codes, {"audio_stream_missing"})
            persisted = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(persisted["status"], "failed")
            self.assertEqual(len(runner.commands), 1)

    def test_hard_gates_report_profile_skew_decode_and_loudness_failures(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            video = root / "final.mp4"
            report_path = root / "final.qa.json"
            video.write_bytes(b"synthetic-mp4")
            runner = StubRunner(
                probe=probe_payload(
                    width=1280,
                    height=720,
                    fps="15/1",
                    video_duration=60,
                    audio_duration=58.8,
                ),
                decode_returncode=1,
                loudness_lufs=-20.0,
                true_peak=-0.2,
            )

            with self.assertRaises(FinalVideoQAError) as raised:
                run_final_video_qa(
                    video,
                    report_path,
                    expected_width=1920,
                    expected_height=1080,
                    expected_fps=24,
                    runner=runner,
                )

            codes = {finding.code for finding in raised.exception.report.findings}
            self.assertEqual(
                codes,
                {
                    "resolution_mismatch",
                    "frame_rate_mismatch",
                    "av_duration_skew",
                    "decode_failed",
                    "loudness_out_of_range",
                    "true_peak_too_high",
                },
            )
            self.assertAlmostEqual(
                raised.exception.report.metrics["av_duration_skew_seconds"], 1.2
            )
            self.assertEqual(
                json.loads(report_path.read_text(encoding="utf-8"))["status"],
                "failed",
            )

    def test_invalid_probe_json_is_a_persisted_hard_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            video = root / "final.mp4"
            report_path = root / "final.qa.json"
            video.write_bytes(b"synthetic-mp4")
            runner = StubRunner(probe_stdout="not-json")

            with self.assertRaises(FinalVideoQAError) as raised:
                run_final_video_qa(video, report_path, runner=runner)

            self.assertEqual(
                [finding.code for finding in raised.exception.report.findings],
                ["probe_invalid_json"],
            )
            self.assertEqual(raised.exception.report.probe, {})
            self.assertTrue(report_path.exists())

    def test_missing_file_does_not_invoke_subprocesses(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            report_path = root / "final.qa.json"
            runner = StubRunner()

            with self.assertRaises(FinalVideoQAError) as raised:
                run_final_video_qa(root / "missing.mp4", report_path, runner=runner)

            self.assertEqual(
                [finding.code for finding in raised.exception.report.findings],
                ["file_missing"],
            )
            self.assertEqual(runner.commands, [])
            self.assertTrue(report_path.exists())


if __name__ == "__main__":
    unittest.main()
