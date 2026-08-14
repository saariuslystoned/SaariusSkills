from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .claude_hook_marker import (
    EVENT_LIMITS,
    RECEIPT_SCHEMA,
    canonical_bytes,
    marker_payload,
    sha256_bytes,
)
from .errors import HerdrPuppetError


LIFECYCLE_SCHEMA = "herdr-puppet.lifecycle-observation.v1"
CLAUDE_STRATEGY = "claude_native_hook_markers"
CHECKPOINT_STRATEGY = "strict_checkpoint_only"
CLAUDE_BASE_FLAGS = ["--dangerously-skip-permissions"]
CLAUDE_HELPER_RELATIVE_PATH = (
    "skills/herdr-puppet/scripts/claude_hook_marker.py"
)
CLAUDE_IMPLEMENTATION_RELATIVE_PATH = (
    "skills/herdr-puppet/scripts/herdr_puppet_lib/claude_hook_marker.py"
)
CLAUDE_MARKER_NAMES = (
    "session_start-0001.json",
    "user_prompt_submit-0001.json",
    "user_prompt_submit-0002.json",
    "stop-0001.json",
    "stop-0002.json",
    "stop_failure-0001.json",
    "stop_failure-0002.json",
    "overflow.json",
)
PHASE_SUBMISSIONS = {"armed": 0, "initial": 1, "steering": 2}

_SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
CLAUDE_HELPER_BOOTSTRAP = """\
import hashlib
import os
import stat
import sys

interpreter_path = sys.argv[1]
interpreter_expected = sys.argv[2]
path = sys.argv[3]
expected = sys.argv[4]
helper_args = sys.argv[5:]

def checked_bytes(path, expected, maximum, require_owner, retain):
    descriptor = None
    try:
        flags = os.O_RDONLY
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NONBLOCK"):
            flags |= os.O_NONBLOCK
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(path, flags)
        identity = os.fstat(descriptor)
        if (
            not stat.S_ISREG(identity.st_mode)
            or (require_owner and identity.st_uid != os.getuid())
            or identity.st_size > maximum
        ):
            raise RuntimeError("unsafe bound executable")
        digest = hashlib.sha256()
        parts = []
        total = 0
        while total <= maximum:
            block = os.read(descriptor, min(65536, maximum + 1 - total))
            if not block:
                break
            total += len(block)
            digest.update(block)
            if retain:
                parts.append(block)
        if total > maximum or digest.hexdigest() != expected:
            raise RuntimeError("bound executable fingerprint changed")
        return b"".join(parts)
    finally:
        if descriptor is not None:
            os.close(descriptor)

result = 0
try:
    if os.path.realpath(sys.executable) != interpreter_path:
        raise RuntimeError("interpreter path changed")
    checked_bytes(
        interpreter_path,
        interpreter_expected,
        134217728,
        False,
        False,
    )
    encoded = checked_bytes(path, expected, 262144, True, True)
    namespace = {
        "__builtins__": __builtins__,
        "__file__": path,
        "__name__": "_herdr_puppet_claude_hook_helper",
        "__package__": None,
    }
    exec(compile(encoded, path, "exec"), namespace)
    helper_main = namespace.get("main")
    if not callable(helper_main):
        raise RuntimeError("helper entrypoint missing")
    result = helper_main(helper_args)
    if isinstance(result, bool) or not isinstance(result, int):
        raise RuntimeError("helper result invalid")
except Exception:
    result = 0 if helper_args and helper_args[0] == "record" else 2
raise SystemExit(result)
"""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            block = stream.read(1024 * 1024)
            if not block:
                return digest.hexdigest()
            digest.update(block)


def _fail(message: str) -> None:
    raise HerdrPuppetError("invalid_lifecycle_observation", message)


def checkpoint_lifecycle_observation() -> dict[str, Any]:
    return {
        "schema": LIFECYCLE_SCHEMA,
        "strategy": CHECKPOINT_STRATEGY,
        "raw_input_retained": False,
    }


def _probe_payload(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": value["schema"],
        "strategy": value["strategy"],
        "run_id": value["run_id"],
        "marker_root": value["marker_root"],
        "interpreter": value["interpreter"],
        "helper": value["helper"],
        "implementation": value["implementation"],
        "event_limits": value["event_limits"],
        "stdin_policy": value["stdin_policy"],
        "stdout_policy": value["stdout_policy"],
        "raw_input_retained": value["raw_input_retained"],
    }


def _hook_handler(
    observation: dict[str, Any],
    event: str,
) -> dict[str, Any]:
    argv = claude_helper_exec_argv(
        observation,
        [
            "record",
            "--root",
            observation["marker_root"],
            "--run-id",
            observation["run_id"],
            "--probe-id",
            observation["probe_id"],
            "--event",
            event,
            "--implementation-sha256",
            observation["implementation"]["sha256"],
        ],
    )
    return {
        "type": "command",
        "command": argv[0],
        "args": argv[1:],
        "timeout": 5,
    }


def claude_helper_exec_argv(
    observation: dict[str, Any],
    helper_args: list[str],
) -> list[str]:
    return [
        observation["interpreter"]["path"],
        "-I",
        "-c",
        CLAUDE_HELPER_BOOTSTRAP,
        observation["interpreter"]["path"],
        observation["interpreter"]["sha256"],
        observation["helper"]["path"],
        observation["helper"]["sha256"],
        *helper_args,
    ]


def claude_hook_settings(observation: dict[str, Any]) -> dict[str, Any]:
    handlers: dict[str, list[dict[str, Any]]] = {}
    event_names = {
        "SessionStart": "session_start",
        "UserPromptSubmit": "user_prompt_submit",
        "Stop": "stop",
        "StopFailure": "stop_failure",
    }
    for hook_name, event in event_names.items():
        group: dict[str, Any] = {
            "hooks": [
                _hook_handler(observation, event)
            ]
        }
        if hook_name == "SessionStart":
            group["matcher"] = "startup"
        handlers[hook_name] = [group]
    return {"hooks": handlers}


def canonical_settings_json(observation: dict[str, Any]) -> str:
    return canonical_bytes(claude_hook_settings(observation)).decode("utf-8")


def build_claude_lifecycle_observation(
    *,
    run_id: str,
    marker_root: str,
    helper_path: str,
    helper_sha256: str,
    implementation_path: str,
    implementation_sha256: str,
    interpreter_path: str,
    interpreter_sha256: str,
) -> dict[str, Any]:
    observation = {
        "schema": LIFECYCLE_SCHEMA,
        "strategy": CLAUDE_STRATEGY,
        "run_id": run_id,
        "marker_root": marker_root,
        "interpreter": {
            "path": interpreter_path,
            "sha256": interpreter_sha256,
            "argv": [interpreter_path, "-I", "-c"],
        },
        "helper": {
            "path": helper_path,
            "sha256": helper_sha256,
        },
        "implementation": {
            "path": implementation_path,
            "sha256": implementation_sha256,
        },
        "event_limits": dict(EVENT_LIMITS),
        "stdin_policy": "user_prompt_hashed_in_memory_other_events_unread",
        "stdout_policy": "empty",
        "raw_input_retained": False,
    }
    observation["probe_id"] = sha256_bytes(
        canonical_bytes(_probe_payload(observation))
    )
    observation["settings_sha256"] = sha256_bytes(
        canonical_bytes(claude_hook_settings(observation))
    )
    return observation


def build_runtime_claude_lifecycle_observation(
    *,
    run_id: str,
    marker_root: str,
    helper_path: Path,
    implementation_path: Path,
    interpreter_path: Path,
) -> dict[str, Any]:
    return build_claude_lifecycle_observation(
        run_id=run_id,
        marker_root=marker_root,
        helper_path=str(helper_path),
        helper_sha256=_sha256_file(helper_path),
        implementation_path=str(implementation_path),
        implementation_sha256=_sha256_file(implementation_path),
        interpreter_path=str(interpreter_path),
        interpreter_sha256=_sha256_file(interpreter_path),
    )


def validate_lifecycle_observation(
    value: Any,
    *,
    harness: str,
    source_worktree: str,
    skill_root: Path | None = None,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail("The lifecycle observation must be an object.")
    observation = dict(value)
    if harness != "claude":
        if observation != checkpoint_lifecycle_observation():
            _fail("Non-Claude harnesses must use strict checkpoint observation.")
        return observation
    expected_fields = {
        "schema",
        "strategy",
        "run_id",
        "probe_id",
        "marker_root",
        "interpreter",
        "helper",
        "implementation",
        "event_limits",
        "settings_sha256",
        "stdin_policy",
        "stdout_policy",
        "raw_input_retained",
    }
    if set(observation) != expected_fields:
        _fail("The Claude lifecycle observation fields are invalid.")
    if (
        observation["schema"] != LIFECYCLE_SCHEMA
        or observation["strategy"] != CLAUDE_STRATEGY
        or observation["stdin_policy"]
        != "user_prompt_hashed_in_memory_other_events_unread"
        or observation["stdout_policy"] != "empty"
        or observation["raw_input_retained"] is not False
        or observation["event_limits"] != EVENT_LIMITS
    ):
        _fail("The Claude lifecycle observation contract changed.")
    if (
        not isinstance(observation["run_id"], str)
        or _SAFE_RUN_ID.fullmatch(observation["run_id"]) is None
    ):
        _fail("The Claude lifecycle run id is invalid.")
    marker_root = observation["marker_root"]
    if (
        not isinstance(marker_root, str)
        or not Path(marker_root).is_absolute()
        or marker_root == "/"
        or "\x00" in marker_root
        or "\n" in marker_root
        or "\r" in marker_root
    ):
        _fail("The Claude lifecycle marker root is invalid.")
    expected_helper_path = (
        Path(source_worktree) / CLAUDE_HELPER_RELATIVE_PATH
    )
    expected_implementation_path = (
        Path(source_worktree) / CLAUDE_IMPLEMENTATION_RELATIVE_PATH
    )
    for field in ("helper", "implementation"):
        record = observation[field]
        if (
            not isinstance(record, dict)
            or set(record) != {"path", "sha256"}
            or not isinstance(record["path"], str)
            or not Path(record["path"]).is_absolute()
            or not isinstance(record["sha256"], str)
            or _SHA256.fullmatch(record["sha256"]) is None
        ):
            _fail(f"The Claude lifecycle {field} identity is invalid.")
    interpreter = observation["interpreter"]
    if (
        not isinstance(interpreter, dict)
        or set(interpreter) != {"path", "sha256", "argv"}
        or not isinstance(interpreter["path"], str)
        or not Path(interpreter["path"]).is_absolute()
        or not isinstance(interpreter["sha256"], str)
        or _SHA256.fullmatch(interpreter["sha256"]) is None
        or interpreter["argv"] != [interpreter["path"], "-I", "-c"]
    ):
        _fail("The Claude lifecycle interpreter identity is invalid.")
    if Path(observation["helper"]["path"]) != expected_helper_path:
        _fail("The Claude lifecycle helper is not source-bound.")
    if (
        Path(observation["implementation"]["path"])
        != expected_implementation_path
    ):
        _fail("The Claude lifecycle implementation is not source-bound.")
    if skill_root is not None:
        local_helper = Path(skill_root) / "scripts" / "claude_hook_marker.py"
        local_implementation = (
            Path(skill_root)
            / "scripts"
            / "herdr_puppet_lib"
            / "claude_hook_marker.py"
        )
        if (
            not local_helper.is_file()
            or local_helper.is_symlink()
            or _sha256_file(local_helper) != observation["helper"]["sha256"]
        ):
            _fail("The Claude lifecycle helper fingerprint changed.")
        if (
            not local_implementation.is_file()
            or local_implementation.is_symlink()
            or _sha256_file(local_implementation)
            != observation["implementation"]["sha256"]
        ):
            _fail("The Claude lifecycle implementation fingerprint changed.")
    expected_probe = sha256_bytes(canonical_bytes(_probe_payload(observation)))
    if (
        not isinstance(observation["probe_id"], str)
        or observation["probe_id"] != expected_probe
    ):
        _fail("The Claude lifecycle probe id is invalid.")
    expected_settings = sha256_bytes(
        canonical_bytes(claude_hook_settings(observation))
    )
    if observation["settings_sha256"] != expected_settings:
        _fail("The Claude lifecycle settings fingerprint changed.")
    return observation


def claude_launch_flags(observation: dict[str, Any]) -> list[str]:
    return [
        *CLAUDE_BASE_FLAGS,
        "--settings",
        canonical_settings_json(observation),
    ]


def validate_claude_hook_receipt(
    value: Any,
    *,
    observation: dict[str, Any],
    phase: str,
    expected_prompt_sha256s: list[str],
) -> tuple[dict[str, Any], str]:
    if phase not in PHASE_SUBMISSIONS:
        raise HerdrPuppetError(
            "invalid_claude_lifecycle_phase",
            "Claude lifecycle phase must be armed, initial, or steering.",
        )
    if not isinstance(value, dict):
        raise HerdrPuppetError(
            "invalid_claude_hook_receipt",
            "The Claude hook receipt must be an object.",
        )
    expected_submissions = PHASE_SUBMISSIONS[phase]
    if (
        not isinstance(expected_prompt_sha256s, list)
        or len(expected_prompt_sha256s) != expected_submissions
        or any(
            not isinstance(prompt_sha256, str)
            or _SHA256.fullmatch(prompt_sha256) is None
            for prompt_sha256 in expected_prompt_sha256s
        )
    ):
        raise HerdrPuppetError(
            "invalid_claude_expected_prompt_history",
            "Claude lifecycle validation requires exact controller prompt fingerprints.",
        )
    receipt = dict(value)
    expected_fields = {
        "schema",
        "run_id",
        "probe_id",
        "markers",
        "counts",
        "marker_set_sha256",
        "stdin_read",
        "raw_input_retained",
        "transcript_read",
    }
    if set(receipt) != expected_fields:
        raise HerdrPuppetError(
            "invalid_claude_hook_receipt",
            "The Claude hook receipt fields are invalid.",
        )
    if (
        receipt["schema"] != RECEIPT_SCHEMA
        or receipt["run_id"] != observation["run_id"]
        or receipt["probe_id"] != observation["probe_id"]
        or not isinstance(receipt["stdin_read"], bool)
        or receipt["raw_input_retained"] is not False
        or receipt["transcript_read"] is not False
        or not isinstance(receipt["markers"], list)
        or not isinstance(receipt["counts"], dict)
        or set(receipt["counts"]) != set(EVENT_LIMITS)
        or any(
            isinstance(count, bool)
            or not isinstance(count, int)
            or count < 0
            for count in receipt["counts"].values()
        )
    ):
        raise HerdrPuppetError(
            "invalid_claude_hook_receipt",
            "The Claude hook receipt does not match its bound probe.",
        )
    calculated_counts = {event: 0 for event in EVENT_LIMITS}
    expected_markers: list[dict[str, Any]] = []
    for marker in receipt["markers"]:
        marker_fields = {"event", "ordinal", "sha256"}
        if isinstance(marker, dict) and marker.get("event") == "user_prompt_submit":
            marker_fields.add("prompt_sha256")
        if (
            not isinstance(marker, dict)
            or set(marker) != marker_fields
            or marker["event"] not in EVENT_LIMITS
            or isinstance(marker["ordinal"], bool)
            or not isinstance(marker["ordinal"], int)
            or marker["ordinal"] < 1
            or marker["ordinal"] > EVENT_LIMITS[marker["event"]]
            or not isinstance(marker["sha256"], str)
            or _SHA256.fullmatch(marker["sha256"]) is None
            or (
                marker["event"] == "user_prompt_submit"
                and (
                    not isinstance(marker.get("prompt_sha256"), str)
                    or _SHA256.fullmatch(marker["prompt_sha256"]) is None
                )
            )
        ):
            raise HerdrPuppetError(
                "invalid_claude_hook_receipt",
                "A Claude hook marker summary is invalid.",
            )
        expected_payload = canonical_bytes(
            marker_payload(
                run_id=observation["run_id"],
                probe_id=observation["probe_id"],
                event=marker["event"],
                ordinal=marker["ordinal"],
                prompt_sha256=marker.get("prompt_sha256"),
            )
        ) + b"\n"
        if marker["sha256"] != sha256_bytes(expected_payload):
            raise HerdrPuppetError(
                "invalid_claude_hook_receipt",
                "A Claude hook marker fingerprint is invalid.",
            )
        calculated_counts[marker["event"]] += 1
        expected_markers.append(dict(marker))
    expected_markers.sort(key=lambda marker: (marker["event"], marker["ordinal"]))
    if receipt["markers"] != expected_markers:
        raise HerdrPuppetError(
            "invalid_claude_hook_receipt",
            "Claude hook marker summaries are not canonically ordered.",
        )
    for event, count in calculated_counts.items():
        if (
            receipt["counts"].get(event) != count
            or [marker["ordinal"] for marker in receipt["markers"] if marker["event"] == event]
            != list(range(1, count + 1))
        ):
            raise HerdrPuppetError(
                "invalid_claude_hook_receipt",
                "Claude hook marker counts or ordinals are invalid.",
            )
    expected_set = sha256_bytes(canonical_bytes(receipt["markers"]))
    if receipt["marker_set_sha256"] != expected_set:
        raise HerdrPuppetError(
            "invalid_claude_hook_receipt",
            "The Claude hook marker-set fingerprint is invalid.",
        )
    counts = receipt["counts"]
    if counts["session_start"] != 1:
        raise HerdrPuppetError(
            "invalid_claude_hook_receipt",
            "The Claude session-start marker is missing or ambiguous.",
        )
    submit_count = counts["user_prompt_submit"]
    terminal_count = counts["stop"] + counts["stop_failure"]
    if (
        submit_count > expected_submissions
        or terminal_count > submit_count
        or counts["stop"] > expected_submissions
        or counts["stop_failure"] > expected_submissions
    ):
        raise HerdrPuppetError(
            "invalid_claude_hook_receipt",
            "Claude lifecycle counts exceed the selected controller phase.",
        )
    observed_prompt_sha256s = [
        marker["prompt_sha256"]
        for marker in receipt["markers"]
        if marker["event"] == "user_prompt_submit"
    ]
    if (
        observed_prompt_sha256s != expected_prompt_sha256s[:submit_count]
        or receipt["stdin_read"] is not bool(submit_count)
    ):
        raise HerdrPuppetError(
            "invalid_claude_hook_receipt",
            "Claude prompt markers do not match exact controller sends.",
        )
    if expected_submissions == 0:
        if submit_count or terminal_count:
            raise HerdrPuppetError(
                "invalid_claude_hook_receipt",
                "The armed receipt already contains a turn.",
            )
        classification = "armed"
    elif submit_count < expected_submissions:
        classification = "submission_not_observed"
    elif terminal_count < submit_count:
        classification = "response_pending"
    elif counts["stop_failure"]:
        classification = "response_failed"
    else:
        classification = "response_completed"
    return receipt, classification
