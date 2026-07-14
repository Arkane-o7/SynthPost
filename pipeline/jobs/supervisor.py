"""Process supervisor for configurable parallel SynthPost queue workers."""

from __future__ import annotations

import argparse
import fcntl
import os
import signal
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass

from pipeline import config
from pipeline.db.sqlite import database_path
from pipeline.models import JobQueueLane


@dataclass(frozen=True, order=True)
class WorkerSpec:
    lane: str
    slot: int

    @property
    def label(self) -> str:
        return f"{self.lane}:{self.slot}"


def configured_worker_specs(
    settings: config.SynthPostSettings | None = None,
) -> tuple[WorkerSpec, ...]:
    snapshot = settings or config.get_settings()
    return tuple(
        WorkerSpec(lane.value, slot)
        for lane in JobQueueLane
        for slot in range(1, snapshot.jobs.workers_for(lane.value) + 1)
    )


def worker_command(spec: WorkerSpec) -> list[str]:
    return [
        sys.executable,
        "-m",
        "pipeline.jobs.worker",
        "--lane",
        spec.lane,
        "--slot",
        str(spec.slot),
    ]


@contextmanager
def supervisor_process_lock():
    lock_path = database_path().with_suffix(".workers.supervisor.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+", encoding="utf-8")
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(
                "Another SynthPost worker supervisor is already running."
            ) from exc
        handle.seek(0)
        handle.truncate()
        handle.write(str(os.getpid()))
        handle.flush()
        yield
    finally:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def _spawn(spec: WorkerSpec) -> tuple[subprocess.Popen[bytes], float]:
    print(f"[workers] starting {spec.label}", flush=True)
    return (
        subprocess.Popen(worker_command(spec), start_new_session=True),
        time.monotonic(),
    )


def _stop_children(
    children: dict[WorkerSpec, tuple[subprocess.Popen[bytes], float]],
) -> None:
    for process, _ in children.values():
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
    deadline = time.monotonic() + 10.0
    for process, _ in children.values():
        if process.poll() is not None:
            continue
        try:
            process.wait(timeout=max(0.1, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    for process, _ in children.values():
        try:
            process.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            pass


def run_supervisor(*, poll_interval: float = 1.0) -> None:
    settings = config.validate_startup()
    specs = configured_worker_specs(settings)
    counts = {
        lane.value: settings.jobs.workers_for(lane.value) for lane in JobQueueLane
    }
    print(
        "[workers] configured capacity: "
        + ", ".join(f"{lane}={count}" for lane, count in counts.items()),
        flush=True,
    )
    stop_requested = threading.Event()

    def request_stop(_signum: int, _frame: object) -> None:
        stop_requested.set()

    previous_handlers = {
        signum: signal.signal(signum, request_stop)
        for signum in (signal.SIGINT, signal.SIGTERM)
    }
    children: dict[WorkerSpec, tuple[subprocess.Popen[bytes], float]] = {}
    quick_failures: dict[WorkerSpec, list[float]] = {spec: [] for spec in specs}
    try:
        with supervisor_process_lock():
            children = {spec: _spawn(spec) for spec in specs}
            while not stop_requested.wait(poll_interval):
                for spec, (process, started_at) in list(children.items()):
                    return_code = process.poll()
                    if return_code is None:
                        continue
                    lifetime = time.monotonic() - started_at
                    print(
                        f"[workers] {spec.label} exited code={return_code} "
                        f"after {lifetime:.1f}s",
                        flush=True,
                    )
                    now = time.monotonic()
                    failures = [
                        value
                        for value in quick_failures[spec]
                        if now - value <= 30.0
                    ]
                    if lifetime < 5.0:
                        failures.append(now)
                    else:
                        failures.clear()
                    quick_failures[spec] = failures
                    if len(failures) >= 3:
                        raise RuntimeError(
                            f"Worker {spec.label} failed three times within 30 seconds; "
                            "stopping the pool instead of restart-looping."
                        )
                    children[spec] = _spawn(spec)
    finally:
        stop_requested.set()
        _stop_children(children)
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the configured SynthPost multi-process worker pool."
    )
    parser.add_argument("--poll-interval", type=float, default=1.0)
    args = parser.parse_args()
    if args.poll_interval <= 0:
        parser.error("--poll-interval must be positive")
    run_supervisor(poll_interval=args.poll_interval)


if __name__ == "__main__":
    main()
