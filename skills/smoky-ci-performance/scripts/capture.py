#!/usr/bin/env python3
"""Record one approved command without a shell, scheduler, or test runner."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Mapping, Sequence

SCHEMA = "smoky-ci-performance.capture.v1"
VERSION = "1"
SUMMARY_KEYS = (
    "classification",
    "raw_exit",
    "normalized_exit",
    "signal",
    "wall_seconds",
    "user_seconds",
    "system_seconds",
    "max_rss",
    "max_rss_unit",
    "cost",
)
HELP = """\
usage: python3 skills/smoky-ci-performance/scripts/capture.py --out DIR -- ARGV...

Run ARGV once with no shell. Stdin is closed. Child stdout and stderr go to
DIR/stdout.txt and DIR/stderr.txt. DIR must be new or empty; a nonempty
directory is refused and is not changed.

capture.json and summary.md are written from the same values after the stream
files are closed. Copy summary.md into reports. Do not retype its numbers.
Cost is unknown. Resource metrics are null when unsupported. macOS max RSS is
bytes; Linux max RSS is KiB. The RSS value is the waited-child maximum, not a
sum and not a process-tree peak.

Do not pass secrets in argv. Argv is recorded exactly. The environment is not
read or recorded. The caller owns context and any external timeout.

exit: command status when the receipt is complete; otherwise 2 usage, 127 not
found, or 1 start/write failure.
"""


class CaptureError(Exception):
    def __init__(self, code: str, message: str, exit_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.exit_code = exit_code


def rss_unit(platform: str) -> str | None:
    # ru_maxrss is bytes on macOS and KiB on Linux. Do not guess elsewhere.
    if platform == "darwin":
        return "bytes"
    if platform.startswith("linux"):
        return "KiB"
    return None


def _number(value: object) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def interpret_resources(sample: object, platform: str) -> dict[str, object]:
    """Map one getrusage sample. Missing data stays null, not zero."""
    if sample is None:
        return {
            "user_seconds": None,
            "system_seconds": None,
            "max_rss": None,
            "max_rss_unit": None,
            "aggregation": None,
        }
    unit = rss_unit(platform)
    max_rss = _number(getattr(sample, "ru_maxrss", None))
    return {
        "user_seconds": _number(getattr(sample, "ru_utime", None)),
        "system_seconds": _number(getattr(sample, "ru_stime", None)),
        "max_rss": max_rss if unit is not None else None,
        "max_rss_unit": unit if max_rss is not None else None,
        "aggregation": "waited-children",
    }


def read_resources() -> dict[str, object]:
    try:
        import resource
    except ImportError:
        return interpret_resources(None, sys.platform)
    getter = getattr(resource, "getrusage", None)
    who = getattr(resource, "RUSAGE_CHILDREN", None)
    if getter is None or who is None:
        return interpret_resources(None, sys.platform)
    try:
        sample = getter(who)
    except (OSError, ValueError):
        return interpret_resources(None, sys.platform)
    return interpret_resources(sample, sys.platform)


def normalize_exit(raw: int) -> dict[str, int | None]:
    if raw < 0:
        signal_number = -raw
        return {
            "raw": raw,
            "normalized": 128 + signal_number,
            "signal": signal_number,
        }
    return {"raw": raw, "normalized": raw, "signal": None}


def empty_exit() -> dict[str, None]:
    return {"raw": None, "normalized": None, "signal": None}


def parse_invocation(argv: Sequence[str]) -> tuple[Path, list[str]]:
    if "--" not in argv:
        raise CaptureError(
            "usage",
            "A -- separator and command argv are required.",
            2,
        )
    separator = argv.index("--")
    options = list(argv[:separator])
    command = list(argv[separator + 1 :])
    if len(options) != 2 or options[0] != "--out" or options[1] == "":
        raise CaptureError("usage", "--out <directory> is required before --.", 2)
    if not command:
        raise CaptureError("usage", "The command argv after -- is empty.", 2)
    return Path(options[1]), command


def accept_output(path: Path) -> None:
    if path.is_symlink():
        raise CaptureError("refused-output", "Refusing a symlink output path.", 2)
    if path.exists():
        if not path.is_dir():
            raise CaptureError("refused-output", "Output path is not a directory.", 2)
        try:
            occupied = any(path.iterdir())
        except OSError as exc:
            raise CaptureError(
                "refused-output",
                "Output directory could not be read.",
                2,
            ) from exc
        if occupied:
            raise CaptureError(
                "refused-output",
                "Refusing nonempty output directory.",
                2,
            )
        return
    parent = path.parent
    if parent != path and not parent.is_dir():
        raise CaptureError(
            "refused-output",
            "Output parent directory does not exist.",
            2,
        )
    try:
        path.mkdir(parents=False, exist_ok=False)
    except OSError as exc:
        raise CaptureError(
            "refused-output",
            "Output directory could not be created.",
            2,
        ) from exc


def base_record(command: list[str] | None, classification: str) -> dict[str, object]:
    return {
        "schema": SCHEMA,
        "classification": classification,
        "argv": command,
        "exit": empty_exit(),
        "wall_seconds": None,
        "resources": interpret_resources(None, sys.platform),
        "metrics_supported": False,
        "cost": "unknown",
        "streams": {"stdout": "stdout.txt", "stderr": "stderr.txt"},
        "error": None,
    }


def failure_record(command: list[str], error: CaptureError) -> dict[str, object]:
    record = base_record(command, "failure")
    record["error"] = {"code": error.code, "message": error.message}
    return record


def complete_record(
    command: list[str],
    raw: int,
    wall_seconds: float,
    resources: Mapping[str, object],
) -> dict[str, object]:
    record = base_record(command, "complete")
    record["exit"] = normalize_exit(raw)
    record["wall_seconds"] = wall_seconds
    record["resources"] = dict(resources)
    record["metrics_supported"] = resources.get("aggregation") is not None
    return record


def summary_line(record: Mapping[str, object]) -> str:
    exit_info = record["exit"]
    resources = record["resources"]
    if not isinstance(exit_info, Mapping) or not isinstance(resources, Mapping):
        raise CaptureError("receipt-invalid", "Capture receipt was incomplete.", 1)
    values: dict[str, object] = {
        "classification": record["classification"],
        "raw_exit": exit_info["raw"],
        "normalized_exit": exit_info["normalized"],
        "signal": exit_info["signal"],
        "wall_seconds": record["wall_seconds"],
        "user_seconds": resources["user_seconds"],
        "system_seconds": resources["system_seconds"],
        "max_rss": resources["max_rss"],
        "max_rss_unit": resources["max_rss_unit"],
        "cost": record["cost"],
    }
    return " ".join(
        f"{key}={json.dumps(values[key], ensure_ascii=False, allow_nan=False)}"
        for key in SUMMARY_KEYS
    )


def render(record: Mapping[str, object]) -> tuple[bytes, bytes]:
    payload = (
        json.dumps(record, indent=2, ensure_ascii=True, allow_nan=False) + "\n"
    ).encode("utf-8")
    # Parse the bytes we are about to publish so a non-JSON receipt cannot land.
    json.loads(payload.decode("utf-8"))
    summary = (summary_line(record) + "\n").encode("utf-8")
    return payload, summary


def publish(directory: Path, record: Mapping[str, object]) -> bytes:
    payload, summary = render(record)
    _replace(directory / "summary.md", summary)
    _replace(directory / "capture.json", payload)
    return payload


def _replace(path: Path, data: bytes) -> None:
    temporary = path.parent / f".{path.name}.tmp"
    with temporary.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def execute(directory: Path, command: list[str]) -> tuple[dict[str, object], int]:
    stdout_path = directory / "stdout.txt"
    stderr_path = directory / "stderr.txt"
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        started = time.monotonic()
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                shell=False,
            )
        except FileNotFoundError as exc:
            raise CaptureError(
                "executable-not-found",
                "Command executable was not found.",
                127,
            ) from exc
        except OSError as exc:
            raise CaptureError(
                "command-start-failed",
                "Command could not be started.",
                1,
            ) from exc
        raw = process.wait()
        wall_seconds = time.monotonic() - started
    return complete_record(command, raw, wall_seconds, read_resources()), raw


def write_error(message: str) -> None:
    sys.stderr.write(f"capture.py: {message}\n")


def echo_receipt(payload: bytes) -> None:
    try:
        sys.stdout.buffer.write(payload)
        sys.stdout.buffer.flush()
    except OSError:
        # The receipt is already durable. If the caller closed stdout, replace
        # the descriptor before shutdown so Python cannot re-flush the broken
        # pipe and change the helper's authoritative child status.
        try:
            devnull = os.open(os.devnull, os.O_WRONLY)
            os.dup2(devnull, sys.stdout.fileno())
            os.close(devnull)
            sys.stdout.buffer.flush()
        except OSError:
            pass


def main(argv: Sequence[str]) -> int:
    if list(argv) in (["-h"], ["--help"]):
        sys.stdout.write(HELP)
        return 0
    if list(argv) == ["--version"]:
        sys.stdout.write(f"capture.py {VERSION}\n")
        return 0
    try:
        directory, command = parse_invocation(argv)
        accept_output(directory)
    except CaptureError as exc:
        write_error(f"classification=incomplete: {exc.message}")
        return exc.exit_code

    status = 1
    try:
        try:
            record, raw = execute(directory, command)
        except CaptureError as exc:
            record = failure_record(command, exc)
            status = exc.exit_code
        else:
            exit_info = record["exit"]
            if isinstance(exit_info, Mapping) and isinstance(
                exit_info.get("normalized"), int
            ):
                status = int(exit_info["normalized"])
            else:
                status = raw if raw >= 0 else 1
        payload = publish(directory, record)
    except (OSError, CaptureError, TypeError, ValueError):
        write_error("classification=failure: could not write the capture receipt")
        return 1
    echo_receipt(payload)
    write_error(f"classification={record['classification']}")
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
