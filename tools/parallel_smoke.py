"""Run multiple isolated TEST_MODE episodes concurrently on one workstation."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import BinaryIO

from pipeline.observability import safe_text
from pipeline.storage import PROJECT_ROOT


def _summary_lines(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    selected = [
        line
        for line in lines
        if line.startswith("Pipeline summary:")
        or line.startswith("[run_episode] Final episode:")
    ]
    return selected or lines[-12:]


def _terminate(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)


def run_parallel_smoke(episode_count: int, render_profile: str) -> int:
    if episode_count < 2:
        raise ValueError("parallel smoke requires at least two episodes")
    if episode_count > 8:
        raise ValueError("parallel smoke is capped at eight episodes")

    environment = os.environ.copy()
    environment["SYNTHPOST_LLM_PROVIDER"] = "mock"
    environment["PYTHONUNBUFFERED"] = "1"
    command = [
        sys.executable,
        "-m",
        "pipeline.run_episode",
        "--smoke",
        "--render-profile",
        render_profile,
    ]
    processes: list[tuple[int, subprocess.Popen[bytes], Path, BinaryIO]] = []
    with tempfile.TemporaryDirectory(prefix="synthpost-parallel-smoke-") as directory:
        log_dir = Path(directory)
        try:
            for index in range(1, episode_count + 1):
                log_path = log_dir / f"episode-{index}.log"
                handle = log_path.open("wb")
                process = subprocess.Popen(
                    command,
                    cwd=PROJECT_ROOT,
                    env=environment,
                    stdout=handle,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
                processes.append((index, process, log_path, handle))
                print(
                    f"[parallel-smoke] started episode {index} pid={process.pid}",
                    flush=True,
                )

            failed = False
            for index, process, log_path, handle in processes:
                return_code = process.wait()
                handle.close()
                print(
                    f"[parallel-smoke] episode {index} exit={return_code}",
                    flush=True,
                )
                for line in _summary_lines(log_path):
                    print(f"  {safe_text(line)}", flush=True)
                failed = failed or return_code != 0
            return int(failed)
        except KeyboardInterrupt:
            return 130
        finally:
            for _, process, _, handle in processes:
                _terminate(process)
                try:
                    handle.close()
                except OSError:
                    pass


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Render and assemble multiple TEST_MODE episodes concurrently."
    )
    parser.add_argument("--episodes", type=int, default=2)
    parser.add_argument(
        "--render-profile",
        choices=["preview", "production", "final_master"],
        default="preview",
    )
    args = parser.parse_args()
    try:
        result = run_parallel_smoke(args.episodes, args.render_profile)
    except ValueError as exc:
        parser.error(str(exc))
    raise SystemExit(result)


if __name__ == "__main__":
    main()
