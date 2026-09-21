#!/usr/bin/env python3
"""v4 Antigravity ACP failure-receipt proof driver.

Task-only observability repair over v3: persist an allowlisted body-free
receipt on ordinary fixture assertion failure as well as success. Default
invocation stays offline and refuses a live provider turn. Product source
is not modified. Frozen v3 evidence is never overwritten.
"""

from __future__ import annotations

import argparse
import errno
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import time
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Dict, Mapping, Optional


DRIVER_FILE = Path(__file__).resolve()
V4_ROOT = DRIVER_FILE.parents[1]
ANTIGRAVITY_ROOT = V4_ROOT.parent
V3_ROOT = ANTIGRAVITY_ROOT / "v3"
WORKTREE = DRIVER_FILE.parents[6]
SCRIPTS = WORKTREE / "skills" / "puppet" / "scripts"
TEMPLATE_ROOT = ANTIGRAVITY_ROOT / "inputs" / "v2-fixture" / "normalize-lines-fixture"
INTENDED_BIN = ANTIGRAVITY_ROOT / "inputs" / "v2-fixture" / "intended" / "bin" / "normalize-lines.mjs"
TASK_RUNS = WORKTREE / "runs" / "puppet-antigravity-v4-failure-receipt-20260921"
PROOF_OWNED_ARTIFACT = TASK_RUNS / "artifacts-refresh-2e05de52" / "acpx-0.18.0.tgz"
ARTIFACT_PREP = (
    WORKTREE / "runs" / "puppet-dual-acp-controller-runs" / "20260921" / "ARTIFACT_PREP.md"
)
FROZEN_V3_DRIVER = V3_ROOT / "driver" / "agy_live_capable_proof_driver.py"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from antigravity_acpx import ACPX_ARTIFACT_PATH, ACPX_ARTIFACT_SHA256, ACPX_MERGE_COMMIT
from puppet_lib.acp_consumer import AcpConsumerOwner, reject_consumer_bodies
from puppet_lib.antigravity_acp import (
    AntigravityAcpNodeRuntime,
    AntigravityAcpSyntheticRuntime,
    DEFAULT_ANTIGRAVITY_MODEL,
    OFFICIAL_ROUTE_KIND,
    RUNTIME_ID,
    RUNTIME_VERSION,
    TRANSPORT_ID,
    require_antigravity_acp_route_binding,
    resolve_antigravity_acp_route_binding,
    test_only_antigravity_synthetic_route_binding,
)
from puppet_lib.cursor_acp import SYNTHETIC_PEER_KIND, test_only_cursor_synthetic_route_binding
from puppet_lib.errors import IdentityError, UnsupportedError, ValidationError
from puppet_lib.session import _antigravity_acp_structured_launch
from puppet_lib.transport import bind_run_transport


EXACT_AGY_MODEL = "gemini-3.8-flash-high"
OWNER_NAME = "antigravity-acpx"
ADAPTER_ID = "antigravity-acpx"
TARGET = "agy"
EXPECTED_ARTIFACT_SHA256 = "5df327172d83644b5f44925386095c8facce28eb78d1ea81f243d7b100d6e614"
EXPECTED_RUNTIME_ENTRY_SHA256 = "ffdb6949b2239d991f63970514ad99677b19db1839313127a55ad9fcd30a4683"
EXPECTED_UPSTREAM = "2e05de525dd1ab62e9e74bf02d91e3638920fcf3"
EXPECTED_UPSTREAM_TREE = "c612e764ead5d8eaa409956fb1b11c008a7579ed"
SOURCE_HEAD = "d5e33f67f6b42384f6feec1d15be3b69b4525eb8"
SOURCE_TREE = "938ef948a6a1218ad055a17d5d297c633b936167"
PINNED_ARTIFACT = WORKTREE / ACPX_ARTIFACT_PATH
FIXTURE_BRANCH = "agy-proof-fixture-v2"
IMPLEMENTATION_JOB_ID = "12791074-59c9-454e-a446-6ca5c7d14214"
OWNER_TASK_ID = "01a0c107-05e0-7a11-b6b2-93a524b63e98"
LAUNCH_INPUT_SCHEMA = "puppet.antigravity-live-launch-input/v4"
OFFICIAL_RESOLVER_NAME = "resolve_antigravity_acp_route_binding"
STAGED_PARENT_RELEASE = "PARENT_ISSUED_RELEASE"
FIRST_TURN_SOURCE = "_antigravity_acp_structured_launch.require_observation"
SECOND_TURN_SOURCE = "owner.next_turn"
PRODUCT_RUNTIME_TIMEOUT_MS = 30000
LOCAL_BACKEND_EXECUTABLE = "localharness_external"
EVIDENCE_SCHEMA = "puppet.antigravity-live-capable-controller-proof/v4"
FENCE_SCHEMA = "puppet.antigravity-live-capable-cleanup-fence/v4"
RECEIPT_SCHEMA = "puppet.antigravity-failure-receipt/v4"
UNKNOWN = "unknown"
OFFICIAL_LIVE_PYTHON = "/opt/homebrew/opt/python@3.14/bin/python3.14"
OFFICIAL_LIVE_DRIVER = V4_ROOT / "driver" / "agy_live_capable_proof_driver.py"
OFFICIAL_LIVE_LAUNCH_INPUT = V4_ROOT / "staged" / "launch-input.contract.json"
FROZEN_V3_INVOCATION = V3_ROOT / "staged" / "live-invocation.json"
ALLOWED_STOP_REASONS = frozenset(
    {
        "end_turn",
        "max_tokens",
        "cancelled",
        "canceled",
        "error",
        "stop",
        "refused",
        "timeout",
        "length",
        "content_filter",
    }
)
LIVE_RELEASE_MISSING = (
    "live Antigravity provider turn requires --live plus a parent-supplied "
    "launch-input file; missing launch-input rejects before process start"
)
LIVE_NOT_AUTHORIZED = "live Antigravity provider turn is not authorized for this offline driver"
EXPECTED_CHANGED_PATHS = frozenset({"bin/normalize-lines.mjs"})
EXPECTED_IMPORTS = {
    "package/dist/agent-registry-Ct2yWPW7.js": "5091abb775cb9cfc36bc210acd84a830bd5a413db2ba61eab8a0ef22817230ba",
    "package/dist/ipc-Bn8rocUR.js": "33b50f531ae5bb3d39a56b9f325249631721aee54c764b1ce5a2f72a1eff98c0",
    "package/dist/queue-owner-runtime-B-uQhwMC.js": "fc4f3b27e6c003646539fc933a38c80886e1cdabf38d6f33a4abc7185d8b0d5b",
    "package/dist/runtime.js": "ffdb6949b2239d991f63970514ad99677b19db1839313127a55ad9fcd30a4683",
    "package/dist/watch-yKB9yCio.js": "06254f5cf0af1ee1b5855c0380469ea5f6b691d7f693cfa519288adb7798c635",
}
BODY_KEYS = frozenset(
    {
        "prompt",
        "response",
        "output",
        "content",
        "text",
        "transcript",
        "title",
        "options",
        "messages",
        "rawInput",
        "rawOutput",
        "body",
    }
)
SECRET_LAUNCH_KEYS = frozenset(
    {
        "credentials",
        "credential",
        "token",
        "password",
        "secret",
        "api_key",
        "argv",
        "args",
        "env",
        "process_env",
        "profile",
        "settings",
        "auth",
        "auth_log",
        "GEMINI_API_KEY",
        "authorization",
    }
)
TASK_TEXT = (
    "Add only bin/normalize-lines.mjs so normalized stdin under --check exits 0 "
    "with OK and CRLF or trailing whitespace under --check exits 1 with NON_NORMALIZED. "
    "Leave tests, package metadata, and unrelated paths unchanged."
)
FOLLOW_UP_TEXT = (
    "Continue the same owned session only if the fixture after checks are still incomplete."
)


class CleanupVisibleError(Exception):
    """Primary assertion and cleanup failure both remain visible."""

    def __init__(self, primary: BaseException, cleanup: BaseException, fence: Optional[Mapping[str, Any]] = None):
        self.primary = primary
        self.cleanup = cleanup
        self.fence = None if fence is None else dict(fence)
        super().__init__(
            "primary assertion failed: %s; cleanup failed: %s"
            % (_short(primary), _short(cleanup))
        )


def _short(exc: BaseException) -> str:
    return str(exc).split("\n", 1)[0][:240]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def private_root(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, 0o700)
    mode = stat.S_IMODE(path.stat().st_mode)
    if path.stat().st_uid != os.getuid() or mode != 0o700:
        raise ValidationError("isolated state root is not current-UID mode 0700")
    return path


def contain_bodies(value: Any, *, label: str) -> None:
    reject_consumer_bodies(value, label=label)
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if key in BODY_KEYS:
                raise ValidationError("%s contains body-bearing field %s" % (label, key))
            contain_bodies(nested, label=label)
    elif isinstance(value, list):
        for nested in value:
            contain_bodies(nested, label=label)


def body_free(value: Mapping[str, Any], *, label: str) -> Dict[str, Any]:
    contain_bodies(value, label=label)
    return dict(value)


def error_label(exc: BaseException) -> Dict[str, str]:
    return {"type": type(exc).__name__, "message": _short(exc)}


def observed_or_unknown(value: Any) -> Any:
    if value is None or value == "":
        return UNKNOWN
    return value


def extract_stop_reason(turn: Any) -> str:
    if not isinstance(turn, Mapping):
        return UNKNOWN
    result = turn.get("result")
    if not isinstance(result, Mapping):
        return UNKNOWN
    reason = result.get("stopReason")
    if reason is None:
        reason = result.get("stop_reason")
    if not isinstance(reason, str) or not reason:
        return UNKNOWN
    if reason in BODY_KEYS or len(reason) > 64:
        return UNKNOWN
    if reason not in ALLOWED_STOP_REASONS and not re.fullmatch(r"[A-Za-z0-9_.-]+", reason):
        return UNKNOWN
    return reason


def install_turn_stop_reason_capture() -> tuple[list[str], Callable[[], None]]:
    captured: list[str] = []
    originals: list[tuple[type, Callable[..., Any]]] = []

    def wrap(cls: type) -> None:
        original = cls.start_turn

        def wrapped(self, payload):  # type: ignore[no-untyped-def]
            turn = original(self, payload)
            captured.append(extract_stop_reason(turn))
            return turn

        originals.append((cls, original))
        cls.start_turn = wrapped  # type: ignore[method-assign]

    wrap(AntigravityAcpNodeRuntime)
    wrap(AntigravityAcpSyntheticRuntime)

    def restore() -> None:
        for cls, original in originals:
            cls.start_turn = original  # type: ignore[method-assign]

    return captured, restore


def incremental_mapping(collector: Callable[[], Dict[str, Any]]) -> Dict[str, Any]:
    try:
        return collector()
    except Exception as exc:
        return {"available": False, "value": UNKNOWN, "error": error_label(exc)}


def v3_path_forbidden(path: Path) -> bool:
    resolved = str(path.resolve())
    return "/antigravity/v3/" in resolved or resolved.endswith("/antigravity/v3")


def allocate_fresh_receipt_path(directory: Path) -> Path:
    destination = Path(directory)
    destination.mkdir(parents=True, exist_ok=True)
    name = "receipt-%s-%s.json" % (
        time.strftime("%Y%m%dT%H%M%S", time.gmtime()),
        uuid.uuid4().hex[:12],
    )
    path = destination / name
    if path.exists() or v3_path_forbidden(path):
        raise ValidationError("refusing to overwrite existing receipt")
    return path


def persist_receipt(path: Path, evidence: Mapping[str, Any]) -> Dict[str, Any]:
    destination = Path(path)
    if v3_path_forbidden(destination):
        raise ValidationError("refusing to write into frozen v3 evidence")
    if destination.exists():
        raise ValidationError("refusing to overwrite existing receipt")
    payload = body_free(dict(evidence), label="persisted receipt")
    destination.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    fd = os.open(str(destination), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        os.write(fd, encoded)
    finally:
        os.close(fd)
    return {
        "path": str(destination.resolve()),
        "sha256": sha256_file(destination),
        "schema": payload.get("schema"),
        "fresh": True,
        "overwrote": False,
    }


def require_exact_agy_model(model: Any, *, label: str = "requested model") -> str:
    if model != EXACT_AGY_MODEL:
        raise ValidationError("%s must be exact %s" % (label, EXACT_AGY_MODEL))
    if "[" in str(model) or "effort" in str(model).lower():
        raise ValidationError("%s must not carry effort" % label)
    return EXACT_AGY_MODEL


def require_synthetic_non_live(binding: Mapping[str, Any]) -> Dict[str, Any]:
    trusted = require_antigravity_acp_route_binding(binding)
    if trusted.get("kind") != SYNTHETIC_PEER_KIND:
        raise ValidationError("offline driver requires the supported local synthetic peer")
    if trusted.get("test_only") is not True:
        raise ValidationError("antigravity-acp synthetic peer remains test-only")
    if trusted.get("kind") == OFFICIAL_ROUTE_KIND or trusted.get("test_only") is False:
        raise ValidationError("synthetic mode cannot produce a live PASS")
    return trusted


def reject_non_official_live_binding(binding: Mapping[str, Any]) -> None:
    if binding.get("kind") == SYNTHETIC_PEER_KIND and binding.get("test_only") is not True:
        raise ValidationError("synthetic peer cannot be claimed as live")
    if binding.get("kind") == OFFICIAL_ROUTE_KIND and binding.get("test_only") is True:
        raise ValidationError("official route cannot be test-only")
    if binding.get("route") != TRANSPORT_ID or binding.get("agent") != "antigravity":
        raise ValidationError("non-official live binding is rejected")
    require_antigravity_acp_route_binding(binding)


def reject_live_claim(*, live: bool, binding: Optional[Mapping[str, Any]] = None) -> None:
    if live:
        raise UnsupportedError(LIVE_NOT_AUTHORIZED)
    if binding is not None and binding.get("kind") == OFFICIAL_ROUTE_KIND:
        raise UnsupportedError(LIVE_NOT_AUTHORIZED)
    if binding is not None and binding.get("test_only") is not True:
        raise ValidationError("non-official live binding is rejected")


def require_launch_input(path: Optional[Path]) -> Dict[str, Any]:
    """Validate a parent-supplied launch-input file before any process starts."""

    if path is None:
        raise UnsupportedError(LIVE_RELEASE_MISSING)
    source = Path(path)
    if not source.is_file():
        raise UnsupportedError(LIVE_RELEASE_MISSING)
    raw = json.loads(source.read_text())
    if not isinstance(raw, Mapping):
        raise ValidationError("launch-input must be a JSON object")
    contain_bodies(raw, label="launch-input")
    extra = set(raw) & SECRET_LAUNCH_KEYS
    if extra:
        raise ValidationError("launch-input contains forbidden secret-bearing field")
    if raw.get("schema") != LAUNCH_INPUT_SCHEMA:
        raise ValidationError("launch-input schema is invalid")
    if raw.get("authorized") is not True:
        raise UnsupportedError(LIVE_NOT_AUTHORIZED)
    release = raw.get("parent_release")
    if not isinstance(release, str) or not release.strip():
        raise UnsupportedError(LIVE_RELEASE_MISSING)
    require_exact_agy_model(raw.get("requested_model"), label="launch-input requested model")
    if raw.get("effort") is not None:
        raise ValidationError("launch-input effort must remain unset")
    if raw.get("apply_known_answer") is True:
        raise ValidationError("live launch-input must not apply the known answer")
    callbacks = raw.get("client_callback_policy") or {"fs": False, "terminal": False}
    if not isinstance(callbacks, Mapping):
        raise ValidationError("launch-input client callback policy is invalid")
    if callbacks.get("fs") is not False or callbacks.get("terminal") is not False:
        raise ValidationError("client callback policy remains fs=false/terminal=false")
    if raw.get("enable_callbacks") is True:
        raise ValidationError("client callbacks must not be enabled from flags alone")
    return {
        "schema": LAUNCH_INPUT_SCHEMA,
        "path": str(source.resolve()),
        "authorized": True,
        "parent_release_present": True,
        "requested_model": EXACT_AGY_MODEL,
        "effort": None,
        "route": TRANSPORT_ID,
        "apply_known_answer": False,
        "client_callback_policy": {"fs": False, "terminal": False},
        "callback_enablement_from_flags": "not_implemented",
        "catalog_injected": False,
    }


def reject_live_without_launch_input(live: bool, launch_input: Optional[Path] = None) -> None:
    if not live:
        return
    require_launch_input(launch_input)


def require_request_match(observation: Mapping[str, Any], request_id: str) -> str:
    result_id = observation.get("terminal", {}).get("result_id") if isinstance(observation, Mapping) else None
    if result_id != request_id:
        raise IdentityError("returned turn request does not match the host request")
    return request_id


def source_identities() -> Dict[str, Any]:
    publication_head = git(WORKTREE, "rev-parse", "HEAD")
    publication_tree = git(WORKTREE, "rev-parse", "HEAD^{tree}")
    files = {
        "session.py": WORKTREE / "skills" / "puppet" / "scripts" / "puppet_lib" / "session.py",
        "acp_consumer.py": WORKTREE / "skills" / "puppet" / "scripts" / "puppet_lib" / "acp_consumer.py",
        "antigravity_acp.py": WORKTREE / "skills" / "puppet" / "scripts" / "puppet_lib" / "antigravity_acp.py",
        "antigravity_acpx.py": WORKTREE / "skills" / "puppet" / "scripts" / "antigravity_acpx.py",
        "controller-runtime-driver.mjs": WORKTREE / "bridge" / "antigravity-acp" / "test" / "controller-runtime-driver.mjs",
        "candidate-peer.mjs": WORKTREE / "bridge" / "antigravity-acp" / "test" / "candidate-peer.mjs",
        "puppet-adapter.mjs": WORKTREE / "bridge" / "cursor-acp" / "puppet-adapter.mjs",
        "ARTIFACT_PREP.md": ARTIFACT_PREP,
    }
    missing = [name for name, path in files.items() if not path.is_file()]
    if missing:
        raise IdentityError("frozen product source files are missing: %s" % ",".join(missing))
    return {
        "source_head": SOURCE_HEAD,
        "source_tree": SOURCE_TREE,
        "frozen_execution_head": SOURCE_HEAD,
        "frozen_execution_tree": SOURCE_TREE,
        "publication_head": publication_head,
        "publication_tree": publication_tree,
        "branch": git(WORKTREE, "branch", "--show-current"),
        "product_source_edits_allowed": False,
        "publication_head_may_differ_from_frozen_execution": True,
        "file_sha256": {name: sha256_file(path) for name, path in files.items()},
    }


def artifact_identities() -> Dict[str, Any]:
    if not PROOF_OWNED_ARTIFACT.is_file() or not PINNED_ARTIFACT.is_file():
        raise IdentityError("pinned public acpx artifact is missing")
    proof_digest = sha256_file(PROOF_OWNED_ARTIFACT)
    pin_digest = sha256_file(PINNED_ARTIFACT)
    if proof_digest != EXPECTED_ARTIFACT_SHA256 or pin_digest != EXPECTED_ARTIFACT_SHA256:
        raise IdentityError("local acpx artifact digest drifted")
    if proof_digest != ACPX_ARTIFACT_SHA256 or ACPX_MERGE_COMMIT != EXPECTED_UPSTREAM:
        raise IdentityError("product artifact identity drifted from ARTIFACT_PREP.md")
    imported = {}
    with tarfile.open(PROOF_OWNED_ARTIFACT, "r:gz") as archive:
        for name, expected in EXPECTED_IMPORTS.items():
            member = archive.extractfile(name)
            if member is None:
                raise IdentityError("artifact import %s is missing" % name)
            digest = sha256_bytes(member.read())
            if digest != expected:
                raise IdentityError("artifact import %s digest drifted" % name)
            imported[name] = digest
    if imported["package/dist/runtime.js"] != EXPECTED_RUNTIME_ENTRY_SHA256:
        raise IdentityError("runtime entry digest drifted")
    return {
        "kind": "local_exact_source_tarball",
        "upstream_commit": EXPECTED_UPSTREAM,
        "upstream_tree": EXPECTED_UPSTREAM_TREE,
        "artifact_path_proof_owned": str(PROOF_OWNED_ARTIFACT),
        "artifact_path_product_pin": ACPX_ARTIFACT_PATH,
        "artifact_sha256": proof_digest,
        "runtime_entry": "package/dist/runtime.js",
        "runtime_entry_sha256": imported["package/dist/runtime.js"],
        "imported_chunks": imported,
        "lifecycle_scripts": "disabled",
        "shared_installation": False,
        "reused": True,
        "rebuilt": False,
    }


def fixture_file_list(root: Path) -> list[str]:
    names = []
    for path in sorted(root.rglob("*")):
        if ".git" in path.parts:
            continue
        if path.is_file():
            names.append(str(path.relative_to(root)))
    return names


def fixture_digests(root: Path) -> Dict[str, str]:
    return {
        "protected_test": sha256_file(root / "test" / "normalize-lines.test.mjs"),
        "library": sha256_file(root / "src" / "normalize-lines.mjs"),
        "package": sha256_file(root / "package.json"),
    }


def run_node_test(workspace: Path) -> Dict[str, Any]:
    completed = subprocess.run(
        ["node", "--test", "--test-reporter=tap", "test/normalize-lines.test.mjs"],
        cwd=str(workspace),
        text=True,
        capture_output=True,
    )
    stream = "%s\n%s" % (completed.stdout, completed.stderr)
    return {
        "exit_code": completed.returncode,
        "pass_count": _node_test_metric(stream, "pass"),
        "fail_count": _node_test_metric(stream, "fail"),
        "stdout_retained": False,
        "stderr_retained": False,
    }


def _node_test_metric(stream: str, name: str) -> int:
    match = re.search(r"(?:#|ℹ)\s+%s\s+(\d+)" % name, stream)
    return int(match.group(1)) if match else 0


def run_check(workspace: Path, payload: bytes) -> Dict[str, Any]:
    completed = subprocess.run(
        ["node", "bin/normalize-lines.mjs", "--check"],
        cwd=str(workspace),
        input=payload,
        capture_output=True,
    )
    marker = completed.stdout.strip().decode("ascii", "replace") if completed.stdout else ""
    if marker not in {"", "OK", "NON_NORMALIZED"}:
        raise ValidationError("fixture check marker is not body-free")
    return {
        "exit_code": completed.returncode,
        "marker": marker or None,
        "stdout_retained": False,
        "stderr_retained": False,
    }


def changed_path_set(workspace: Path) -> set[str]:
    names: set[str] = set()
    porcelain = git(workspace, "status", "--porcelain=v1", "-uall")
    for line in porcelain.splitlines():
        if len(line) < 4:
            continue
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        names.add(path)
    return names


def require_exact_changed_paths(workspace: Path, expected: Optional[set[str]] = None) -> list[str]:
    observed = changed_path_set(workspace)
    wanted = expected if expected is not None else set(EXPECTED_CHANGED_PATHS)
    if observed != wanted:
        raise ValidationError(
            "complete changed-path set must equal exactly %s, got %s"
            % (sorted(wanted), sorted(observed))
        )
    return sorted(observed)


def create_fixture_workspace(destination: Path) -> Dict[str, Any]:
    destination = Path(destination)
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(TEMPLATE_ROOT, destination)
    subprocess.check_call(["git", "init", "-b", FIXTURE_BRANCH], cwd=str(destination), stdout=subprocess.DEVNULL)
    subprocess.check_call(["git", "-C", str(destination), "config", "user.name", "agy-v2-proof"])
    subprocess.check_call(["git", "-C", str(destination), "config", "user.email", "offline@example.invalid"])
    subprocess.check_call(
        ["git", "-C", str(destination), "add", "package.json", "src/normalize-lines.mjs", "test/normalize-lines.test.mjs"]
    )
    subprocess.check_call(["git", "-C", str(destination), "commit", "-m", "baseline 1 pass / 1 missing --check"], cwd=str(destination), stdout=subprocess.DEVNULL)
    identity = workspace_snapshot(destination)
    if identity["branch"] != FIXTURE_BRANCH:
        raise ValidationError("fresh fixture workspace branch is not %s" % FIXTURE_BRANCH)
    return identity


def apply_intended_implementation(workspace: Path) -> str:
    """OFFLINE-ONLY known-answer. Live mode must never call this after launch."""

    target = workspace / "bin" / "normalize-lines.mjs"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(INTENDED_BIN, target)
    os.chmod(target, 0o755)
    return sha256_file(target)


def make_contract(workspace: Path, *, requested_model: str = EXACT_AGY_MODEL) -> Any:
    selected = require_exact_agy_model(requested_model)
    return SimpleNamespace(
        repo=workspace,
        requested_model=selected,
        target=TARGET,
        controller=OWNER_NAME,
    )


def workspace_snapshot(workspace: Path) -> Dict[str, str]:
    return {
        "path": str(Path(workspace).resolve()),
        "branch": git(workspace, "branch", "--show-current"),
        "head": git(workspace, "rev-parse", "HEAD"),
        "tree": git(workspace, "rev-parse", "HEAD^{tree}"),
    }


def helper_child_identity(owner: AcpConsumerOwner, continuation: Mapping[str, Any]) -> Dict[str, Any]:
    """runtime.child_process_identity is the Node driver/helper PID only."""

    record = owner.resolve(continuation)
    runtime = getattr(record["runner"], "runtime", None)
    identity = (
        runtime.child_process_identity()
        if runtime is not None
        else {"pid": None, "returncode": None, "exited": False, "kind": "missing"}
    )
    contain_bodies(identity, label="helper identity")
    labeled = dict(identity)
    labeled["role"] = "node_driver_helper"
    labeled["note"] = (
        "runtime.child_process_identity is the Node controller-runtime-driver/"
        "helper PID only; it is not automatically the AGY backend worker"
    )
    return labeled


def incarnation_fields(identity: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "pid": identity.get("pid"),
        "ppid": identity.get("ppid"),
        "executable_name": identity.get("executable_name"),
        "start_birth_identity": identity.get("start_birth_identity"),
    }


def _ps_identity(pid: int) -> Optional[Dict[str, Any]]:
    """Bounded read-only OS metadata: PID, PPID, executable name, start/birth."""

    completed = subprocess.run(
        ["ps", "-p", str(pid), "-o", "pid=", "-o", "ppid=", "-o", "comm="],
        text=True,
        capture_output=True,
        check=False,
        timeout=5,
    )
    if completed.returncode != 0 or not completed.stdout.strip():
        return None
    parts = completed.stdout.strip().split(None, 2)
    if len(parts) < 3:
        return None
    start = subprocess.run(
        ["ps", "-p", str(pid), "-o", "lstart="],
        text=True,
        capture_output=True,
        check=False,
        timeout=5,
    )
    command = subprocess.run(
        ["ps", "-p", str(pid), "-o", "command="],
        text=True,
        capture_output=True,
        check=False,
        timeout=5,
    )
    command_line = command.stdout.strip() if command.returncode == 0 else ""
    return {
        "pid": int(parts[0]),
        "ppid": int(parts[1]),
        "executable_name": _executable_name_from_ps(parts[2], command_line),
        "start_birth_identity": start.stdout.strip() if start.returncode == 0 else None,
    }


def _executable_name_from_ps(comm: str, command_line: str) -> str:
    """Return executable basename only. Never retain argv/env/secrets."""

    comm_name = Path(comm).name
    candidates = [comm_name]
    if command_line:
        for token in command_line.split()[:2]:
            name = Path(token).name
            if name and name not in candidates:
                candidates.append(name)
    for name in candidates:
        if name in _BACKEND_EXECUTABLE_NAMES:
            return name
        for official in _BACKEND_EXECUTABLE_NAMES:
            if official.startswith(name) and len(name) >= 15:
                return official
    return comm_name


def _owned_descendants(root_pid: int, *, limit: int = 32) -> list[Dict[str, Any]]:
    """Exact descendants of one owned root PID. No broad process table scan."""

    found: list[Dict[str, Any]] = []
    queue = [int(root_pid)]
    seen = {int(root_pid)}
    while queue and len(found) < limit:
        parent = queue.pop(0)
        completed = subprocess.run(
            ["pgrep", "-P", str(parent)],
            text=True,
            capture_output=True,
            check=False,
            timeout=5,
        )
        if completed.returncode not in {0, 1} or not completed.stdout.strip():
            continue
        for token in completed.stdout.split():
            try:
                pid = int(token)
            except ValueError:
                continue
            if pid in seen:
                continue
            seen.add(pid)
            identity = _ps_identity(pid)
            if identity is None:
                continue
            found.append(identity)
            queue.append(pid)
    return found


_BACKEND_EXECUTABLE_NAMES = frozenset(
    {
        "agy_acp_server.par",
        "agy_acp_server.exe",
        "localharness_external",
        "localharness_external.exe",
    }
)


def _backend_named(identity: Mapping[str, Any]) -> bool:
    name = Path(str(identity.get("executable_name") or "")).name
    return name in _BACKEND_EXECUTABLE_NAMES


def pid_is_alive(pid: int) -> Optional[bool]:
    """True if reachable, False if positively absent, None if lookup is uncertain.

    ESRCH / ProcessLookupError is positive absence. Permission or any other
    OSError is unknown and must not be treated as termination.
    """

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return None
    except OSError as exc:
        if getattr(exc, "errno", None) == errno.ESRCH:
            return False
        return None
    return True


def backend_cleanup_policy(*, live: bool, used_kind: str) -> str:
    """Official/live or otherwise provider-capable routes need an explicit fence."""

    if used_kind == OFFICIAL_ROUTE_KIND:
        return "official"
    if live and used_kind != SYNTHETIC_PEER_KIND:
        return "provider_capable"
    return "synthetic"


def start_owned_local_backend(directory: Path) -> Dict[str, Any]:
    """Start a task-owned local peer named localharness_external. Not an AGY claim."""

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    executable = directory / LOCAL_BACKEND_EXECUTABLE
    stop_path = directory / "stop-owned-local-backend"
    if stop_path.exists():
        stop_path.unlink()
    executable.write_text(
        "#!/bin/sh\nwhile [ ! -f \"$1\" ]; do sleep 0.05; done\n",
        encoding="ascii",
    )
    os.chmod(executable, 0o755)
    proc = subprocess.Popen(
        [str(executable), str(stop_path)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    identity = None
    for _ in range(20):
        identity = _ps_identity(proc.pid)
        if identity is not None and identity.get("executable_name") == LOCAL_BACKEND_EXECUTABLE:
            break
        time.sleep(0.05)
    if identity is None:
        proc.terminate()
        proc.wait(timeout=5)
        raise ValidationError("owned local backend incarnation was not observed")
    contain_bodies(identity, label="owned local backend identity")
    return {
        "role": "owned_local_peer_backend",
        "agy_backend_claimed": False,
        "stop_path": str(stop_path),
        "pid": proc.pid,
        "proc": proc,
        "incarnation": incarnation_fields(identity),
    }


def stop_owned_local_backend(handle: Mapping[str, Any]) -> None:
    stop_path = Path(str(handle["stop_path"]))
    stop_path.write_text("stop\n", encoding="ascii")
    proc = handle.get("proc")
    if proc is not None:
        proc.wait(timeout=10)


def observe_helper_and_backend(
    helper_identity: Mapping[str, Any],
    *,
    sampled_after: str,
    os_descendants: Optional[list[Mapping[str, Any]]] = None,
    backend_incarnations: Optional[list[Mapping[str, Any]]] = None,
    extra_owned_pids: Optional[list[int]] = None,
) -> Dict[str, Any]:
    helper_pid = helper_identity.get("pid")
    helper_os = _ps_identity(int(helper_pid)) if isinstance(helper_pid, int) else None
    if os_descendants is None:
        descendants = _owned_descendants(int(helper_pid)) if isinstance(helper_pid, int) else []
        for extra in extra_owned_pids or ():
            if not isinstance(extra, int):
                continue
            identity = _ps_identity(extra)
            if identity is None:
                continue
            if any(item.get("pid") == identity["pid"] for item in descendants):
                continue
            descendants.append(identity)
    else:
        descendants = [incarnation_fields(item) for item in os_descendants]
    if backend_incarnations is None:
        matched = [incarnation_fields(item) for item in descendants if _backend_named(item)]
    else:
        matched = [incarnation_fields(item) for item in backend_incarnations]
    living = []
    terminated = []
    for item in matched:
        pid = item.get("pid")
        current = _ps_identity(int(pid)) if isinstance(pid, int) else None
        same_birth = (
            current is not None
            and current.get("start_birth_identity") == item.get("start_birth_identity")
        )
        if same_birth and pid_is_alive(int(pid)):
            living.append(item)
        else:
            terminated.append(item)
    observed = bool(matched)
    if observed:
        gap = None
    else:
        gap = (
            "no owned descendant matched agy_acp_server/localharness_external; "
            "backend worker identity is unavailable and is not guessed from the "
            "Node helper PID or a generic node child"
        )
    return {
        "sampled_after": sampled_after,
        "first_turn_source": FIRST_TURN_SOURCE,
        "owner_next_turn_is_first_turn": False,
        "helper": {
            "role": "node_driver_helper",
            "source": "runtime.child_process_identity",
            "note": (
                "Node controller-runtime-driver/helper PID; not automatically an AGY backend PID"
            ),
            "pid": helper_pid,
            "returncode": helper_identity.get("returncode"),
            "exited": helper_identity.get("exited"),
            "kind": helper_identity.get("kind"),
        },
        "os_helper": helper_os,
        "owned_descendants": descendants,
        "backend": {
            "role": "owned_backend_incarnation",
            "observed": observed,
            "child_count": len(matched),
            "incarnations": matched,
            "living_count": len(living),
            "terminated_count": len(terminated),
            "terminated": observed and not living,
            "inferred_from_helper_exit": False,
            "helper_exit_sufficient": False,
            "agy_backend_claimed": False,
            "evidence_gap": gap,
        },
    }


def merge_backend_incarnations(*observations: Optional[Mapping[str, Any]]) -> list[Dict[str, Any]]:
    merged: list[Dict[str, Any]] = []
    seen = set()
    for observation in observations:
        if not observation:
            continue
        backend = observation.get("backend") or {}
        for item in backend.get("incarnations") or []:
            key = (
                item.get("pid"),
                item.get("ppid"),
                item.get("executable_name"),
                item.get("start_birth_identity"),
            )
            if key in seen:
                continue
            seen.add(key)
            merged.append(incarnation_fields(item))
    return merged


_PROVIDER_CAPABLE_CLEANUP_POLICIES = frozenset({"official", "live", "provider_capable"})
_METADATA_LOOKUP_ERRORS = (OSError, subprocess.SubprocessError, ValueError, TypeError)


def _meaningful_birth_identity(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def evaluate_backend_after_finish(
    incarnations: list[Mapping[str, Any]],
    *,
    policy: str = "synthetic",
) -> Dict[str, Any]:
    """Re-observe the captured backend incarnation only. Helper exit never counts.

    Missing, denied, or malformed process metadata, and unknown liveness, stay
    cleanup_uncertain. Only positive absence or a validated different
    incarnation may be terminated. Official/live or provider-capable empty
    capture writes the replacement-blocking fence; explicit synthetic
    no-backend proof may keep cleanup_uncertain false.
    """

    surviving = []
    terminated = []
    uncertain = []
    for item in incarnations:
        captured = incarnation_fields(item)
        pid = item.get("pid")
        if not isinstance(pid, int):
            uncertain.append(captured)
            continue
        captured_birth = captured.get("start_birth_identity")
        if not _meaningful_birth_identity(captured_birth):
            uncertain.append(captured)
            continue
        metadata_unknown = False
        try:
            current = _ps_identity(pid)
        except _METADATA_LOOKUP_ERRORS:
            current = None
            metadata_unknown = True
        try:
            alive = pid_is_alive(pid)
        except _METADATA_LOOKUP_ERRORS:
            alive = None
        if metadata_unknown or alive is None:
            uncertain.append(captured)
            continue
        if current is None:
            if alive is False:
                terminated.append(captured)
            else:
                uncertain.append(captured)
            continue
        current_birth = current.get("start_birth_identity")
        if not _meaningful_birth_identity(current_birth):
            uncertain.append(captured)
            continue
        same_incarnation = current_birth == captured_birth
        if same_incarnation and alive is True:
            surviving.append(captured)
        elif not same_incarnation:
            terminated.append(captured)
        elif alive is False:
            terminated.append(captured)
        else:
            uncertain.append(captured)
    if not incarnations:
        result = {
            "matched": False,
            "observed": False,
            "terminated": False,
            "surviving_count": 0,
            "terminated_count": 0,
            "surviving": [],
            "inferred_from_helper_exit": False,
            "helper_exit_sufficient": False,
            "agy_backend_claimed": False,
            "cleanup_uncertain": False,
            "replacement_blocked": False,
            "evidence_gap": (
                "owned backend incarnation was not captured; helper exit is not backend proof"
            ),
        }
        if policy in _PROVIDER_CAPABLE_CLEANUP_POLICIES:
            result.update(
                {
                    "cleanup_uncertain": True,
                    "replacement_blocked": True,
                    "reason": (
                        "official/live or provider-capable backend cleanup is unobservable; "
                        "helper exit and backend-discard acknowledgement are not backend proof"
                    ),
                }
            )
        return result
    if surviving:
        return {
            "matched": True,
            "observed": True,
            "terminated": False,
            "surviving_count": len(surviving),
            "terminated_count": len(terminated),
            "surviving": surviving,
            "inferred_from_helper_exit": False,
            "helper_exit_sufficient": False,
            "agy_backend_claimed": False,
            "cleanup_uncertain": True,
            "replacement_blocked": True,
            "reason": "captured owned backend incarnation survived owner.finish",
        }
    if uncertain:
        return {
            "matched": True,
            "observed": True,
            "terminated": False,
            "surviving_count": 0,
            "terminated_count": len(terminated),
            "surviving": [],
            "inferred_from_helper_exit": False,
            "helper_exit_sufficient": False,
            "agy_backend_claimed": False,
            "cleanup_uncertain": True,
            "replacement_blocked": True,
            "reason": (
                "captured owned backend incarnation metadata or liveness is unknown; "
                "missing lookup is not termination"
            ),
        }
    return {
        "matched": True,
        "observed": True,
        "terminated": True,
        "surviving_count": 0,
        "terminated_count": len(terminated),
        "surviving": [],
        "inferred_from_helper_exit": False,
        "helper_exit_sufficient": False,
        "agy_backend_claimed": False,
        "cleanup_uncertain": False,
        "replacement_blocked": False,
    }


def write_cleanup_fence(
    *,
    fence_dir: Path,
    session: str,
    reason: str,
    helper_pid: Any,
    workspace: Path,
    state_root: Path,
    extra: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    fence_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": FENCE_SCHEMA,
        "cleanup_uncertain": True,
        "replacement_blocked": True,
        "session_replaced": False,
        "workspace_deleted": False,
        "state_deleted": False,
        "session": session,
        "reason": reason,
        "helper_pid": helper_pid,
        "workspace": str(Path(workspace).resolve()),
        "state_root": str(Path(state_root).resolve()),
        "owner_finish_only": True,
        "unrelated_process_kill": False,
        "helper_exit_sufficient": False,
        "owner_id": None,
        "continuation_id": None,
    }
    if extra:
        payload.update(dict(extra))
    contain_bodies(payload, label="cleanup fence")
    path = fence_dir / ("%s-cleanup-uncertain.json" % session)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    payload["path"] = str(path)
    payload["sha256"] = sha256_file(path)
    return payload


def evaluate_helper_exit(child_exit: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    if child_exit.get("exited") is not True:
        return {
            "cleanup_uncertain": True,
            "replacement_blocked": True,
            "reason": "owned Node helper exit was not proven",
        }
    pid = child_exit.get("pid")
    if not isinstance(pid, int):
        return None
    try:
        os.kill(pid, 0)
    except OSError:
        return None
    return {
        "cleanup_uncertain": True,
        "replacement_blocked": True,
        "reason": "owned Node helper pid is still alive",
    }


def accept_unsupported_backend_discard(
    finish: Mapping[str, Any],
    helper: Mapping[str, Any],
    backend: Mapping[str, Any],
) -> Dict[str, Any]:
    """Unsupported backend discard is accepted only with helper and backend proof."""

    backend_discard = finish.get("backend_discard")
    local_release = finish.get("local_release")
    helper_exited = helper.get("exited") is True
    backend_terminated = backend.get("terminated") is True and backend.get("observed") is True
    distinct = {
        "backend_discard": backend_discard,
        "local_release": local_release,
        "final_discard": finish.get("final_discard"),
        "helper_exited": helper_exited,
        "backend_observed": backend.get("observed"),
        "backend_terminated": backend_terminated,
        "helper_exit_sufficient": False,
        "inferred_from_helper_exit": False,
        "conflated": backend_discard == local_release and backend_discard not in {None, False},
    }
    if backend_discard != "unsupported_local_cleanup_proved":
        return {"accepted": False, "reason": "backend discard is not the unsupported-local-proved case", **distinct}
    if not helper_exited or not backend_terminated:
        raise ValidationError(
            "unsupported backend discard is accepted only with exact local helper "
            "exit and independently established backend-worker termination; "
            "otherwise the uncertainty fence is retained"
        )
    return {"accepted": True, "reason": "helper exit and backend termination independently established", **distinct}


def official_route_resolver() -> Dict[str, Any]:
    return resolve_antigravity_acp_route_binding()


def model_evidence(
    launched: Mapping[str, Any],
    *,
    live: bool,
    catalog_injected: bool,
    used_kind: str,
) -> Dict[str, Any]:
    if live and catalog_injected:
        raise ValidationError("official branch must not inject synthetic catalog or current-model evidence")
    model = launched["antigravity_acp"]["model"]
    require_exact_agy_model(model["requested_id"], label="requested model")
    require_exact_agy_model(model["observed_id"], label="current model")
    if model.get("effort") is not None:
        raise ValidationError("AGY effort must remain unset")
    if EXACT_AGY_MODEL not in model.get("advertised_ids", []):
        raise IdentityError("exact AGY model is not advertised")
    from_actual_official = live and used_kind != SYNTHETIC_PEER_KIND and not catalog_injected
    evidence = {
        "requested_model": model["requested_id"],
        "advertised_models": list(model["advertised_ids"]),
        "selected_model": model["requested_id"],
        "current_model": model["observed_id"],
        "selection_state": model["selection_state"],
        "effort": None,
        "source": "actual_route" if from_actual_official else "synthetic_offline_substitute",
        "catalog_injected": catalog_injected,
        "synthetic_model_used_as_live": False,
    }
    contain_bodies(evidence, label="model evidence")
    return evidence


def identity_mapping(continuation: Mapping[str, Any]) -> Dict[str, Any]:
    contain_bodies(continuation, label="continuation")
    host = {
        "session": continuation["session"],
        "host_conversation_id": continuation["host_conversation_id"],
        "request_id": continuation["request_id"],
    }
    runtime = {
        "runtime_session_name": continuation["runtime_session_name"],
        "backend_session_id": continuation["backend_session_id"],
        "acpx_record_id": continuation["acpx_record_id"],
    }
    host_correlation = {
        value
        for value in (host["host_conversation_id"], host["request_id"])
        if value not in {None, ""}
    }
    runtime_ids = {value for value in runtime.values() if value not in {None, ""}}
    if host_correlation & runtime_ids:
        raise IdentityError("runtime identities must not be fabricated from host correlation")
    return {
        "host": host,
        "runtime": runtime,
        "session_to_acpx_record": host["session"] == runtime["acpx_record_id"],
        "process_local": continuation["process_local"],
        "cross_process_resume": continuation["cross_process_resume"],
        "owner_id": continuation["owner_id"],
        "continuation_id": continuation["continuation_id"],
        "route": continuation["route"],
    }


def finish_owned(owner: AcpConsumerOwner, continuation: Mapping[str, Any]) -> Dict[str, Any]:
    closed = owner.finish(continuation)
    contain_bodies(closed, label="owner finish")
    child = closed.get("child_exit") or {}
    if child.get("exited") is not True:
        raise ValidationError("task-owned Node helper cleanup is uncertain")
    if child.get("pid") is not None:
        try:
            os.kill(int(child["pid"]), 0)
        except OSError:
            pass
        else:
            raise ValidationError("task-owned Node helper is still reachable after finish")
    return {
        "local_release": closed.get("local_release"),
        "persistent_state": closed.get("persistent_state"),
        "final_discard": closed.get("final_discard"),
        "backend_discard": closed.get("backend_discard"),
        "child_exit": dict(child),
        "cleanup_fence": None,
        "backend_distinct_from_local_release": closed.get("backend_discard") != closed.get("local_release"),
    }


def collect_fixture_after(
    workspace: Path,
    *,
    protected: Mapping[str, str],
    label: str,
    require_implementation: bool,
) -> Dict[str, Any]:
    tests = run_node_test(workspace)
    errors: list[str] = []
    normalized = None
    dirty = None
    if require_implementation:
        if tests["pass_count"] != 2 or tests["fail_count"] != 0 or tests["exit_code"] != 0:
            errors.append("fixture after tests did not pass independently")
        else:
            try:
                normalized = run_check(workspace, b"ok\n")
                if normalized["exit_code"] != 0 or normalized["marker"] != "OK":
                    errors.append("normalized --check after state failed")
            except Exception as exc:
                errors.append(_short(exc) or "normalized --check after state failed")
            try:
                dirty = run_check(workspace, b"bad  \r\n")
                if dirty["exit_code"] != 1 or dirty["marker"] != "NON_NORMALIZED":
                    errors.append("non-normalized --check after state failed")
            except Exception as exc:
                errors.append(_short(exc) or "non-normalized --check after state failed")
    current = fixture_digests(workspace)
    if current != dict(protected):
        errors.append("protected fixture files changed")
    observed_changed = sorted(changed_path_set(workspace))
    wanted = sorted(EXPECTED_CHANGED_PATHS)
    if require_implementation and observed_changed != wanted:
        errors.append(
            "complete changed-path set must equal exactly %s, got %s"
            % (wanted, observed_changed)
        )
    return {
        "ok": not errors,
        "independent": True,
        "label": label,
        "tests": tests,
        "check_normalized": normalized,
        "check_dirty": dirty,
        "protected_digests": current,
        "protected_unchanged": current == dict(protected),
        "changed_paths": observed_changed,
        "expected_changed_paths": wanted,
        "bin_present": (Path(workspace) / "bin" / "normalize-lines.mjs").is_file(),
        "errors": errors,
        "primary_error": None if not errors else errors[0],
        "agy_useful_edit_unproven": True,
        "qualifying_pass": False,
    }


def inspect_fixture_after(
    workspace: Path,
    *,
    protected: Mapping[str, str],
    label: str,
    require_implementation: bool,
) -> Dict[str, Any]:
    outcome = collect_fixture_after(
        workspace,
        protected=protected,
        label=label,
        require_implementation=require_implementation,
    )
    if require_implementation and not outcome["ok"]:
        raise ValidationError(outcome["primary_error"] or "fixture after assertion failed")
    return {
        "label": outcome["label"],
        "tests": outcome["tests"],
        "check_normalized": outcome["check_normalized"],
        "check_dirty": outcome["check_dirty"],
        "protected_digests": outcome["protected_digests"],
        "changed_paths": outcome["changed_paths"],
        "agy_useful_edit_unproven": True,
    }


def staged_live_invocation() -> Dict[str, Any]:
    command = [
        OFFICIAL_LIVE_PYTHON,
        str(OFFICIAL_LIVE_DRIVER),
        "--live",
        "--launch-input",
        str(OFFICIAL_LIVE_LAUNCH_INPUT),
        "--mode",
        "lifecycle",
    ]
    return {
        "executed": False,
        "command": command,
        "cwd": str(WORKTREE),
        "requested_model": EXACT_AGY_MODEL,
        "effort": None,
        "route_resolver": OFFICIAL_RESOLVER_NAME,
        "structured_launch": "_antigravity_acp_structured_launch",
        "first_turn_source": FIRST_TURN_SOURCE,
        "owner_next_turn_is_first_turn": False,
        "official_route_kind": OFFICIAL_ROUTE_KIND,
        "apply_known_answer": False,
        "catalog_injected": False,
        "client_callback_policy": {"fs": False, "terminal": False},
        "callback_enablement_from_flags": "not_implemented",
        "product_runtime_timeout_ms": PRODUCT_RUNTIME_TIMEOUT_MS,
        "product_timeout_feature_added": False,
        "parent_live_allocation": "one session, at most 2 prompts <=300000ms each, no retry",
        "launch_input_contract": str(OFFICIAL_LIVE_LAUNCH_INPUT),
        "driver": str(OFFICIAL_LIVE_DRIVER),
        "contract_schema": LAUNCH_INPUT_SCHEMA,
        "evidence_schema": EVIDENCE_SCHEMA,
        "historical_v3_to_v2_invocation": str(FROZEN_V3_INVOCATION),
        "historical_v3_to_v2_quarantined": True,
        "note": "staged only; v4 implementation job must not execute this invocation",
    }


def write_staged_artifacts() -> Dict[str, str]:
    staged_dir = V4_ROOT / "staged"
    staged_dir.mkdir(parents=True, exist_ok=True)
    contract = {
        "schema": LAUNCH_INPUT_SCHEMA,
        "authorized": True,
        "parent_release": STAGED_PARENT_RELEASE,
        "requested_model": EXACT_AGY_MODEL,
        "effort": None,
        "route": TRANSPORT_ID,
        "apply_known_answer": False,
        "client_callback_policy": {"fs": False, "terminal": False},
        "enable_callbacks": False,
        "note": "parent-supplied gate only; no credentials, profile, argv, or env secrets",
    }
    contain_bodies(contract, label="staged launch-input")
    contract_path = staged_dir / "launch-input.contract.json"
    contract_path.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n")
    invocation = staged_live_invocation()
    invocation_path = staged_dir / "live-invocation.json"
    invocation_path.write_text(json.dumps(invocation, indent=2, sort_keys=True) + "\n")
    return {"launch_input": str(contract_path), "invocation": str(invocation_path)}


def consume(
    *,
    live: bool = False,
    launch_input: Optional[Path] = None,
    state_root: Optional[Path] = None,
    fixture_dir: Optional[Path] = None,
    session: Optional[str] = None,
    continue_turn: bool = True,
    inspect_after: Optional[bool] = None,
    route_resolver: Optional[Callable[[], Any]] = None,
    structured_launch: Optional[Callable[..., Any]] = None,
    inject_post_launch_failure: Optional[str] = None,
    retain_owned_runtime: Optional[Dict[str, Any]] = None,
    apply_known_answer: Optional[bool] = None,
    inject_unsupported_backend_close: bool = False,
    inject_backend_incarnations: Optional[list[Mapping[str, Any]]] = None,
    inject_os_descendants: Optional[list[Mapping[str, Any]]] = None,
    extra_owned_pids: Optional[list[int]] = None,
    stop_owned_backends: Optional[Callable[[], None]] = None,
    after_turns: Optional[Callable[[Path], None]] = None,
    receipt_path: Optional[Path] = None,
    receipt_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    reject_live_without_launch_input(live, launch_input)
    launch_gate = require_launch_input(launch_input) if live else None
    launch = structured_launch or _antigravity_acp_structured_launch
    session_id = session or ("agy-proof-v4-live" if live else "agy-proof-v4-offline")
    owned_state = Path(state_root) if state_root is not None else V4_ROOT / "state" / session_id
    private_root(owned_state)
    workspace_dir = Path(fixture_dir) if fixture_dir is not None else V4_ROOT / "workspaces" / session_id
    workspace = create_fixture_workspace(workspace_dir)
    baseline_tests = run_node_test(workspace_dir)
    if baseline_tests["pass_count"] != 1 or baseline_tests["fail_count"] != 1 or baseline_tests["exit_code"] == 0:
        raise ValidationError("fixture baseline must be exactly one pass and one missing --check failure")
    protected = fixture_digests(workspace_dir)
    resolver = route_resolver
    if resolver is None:
        resolver = resolve_antigravity_acp_route_binding if live else test_only_antigravity_synthetic_route_binding
    catalog = None
    intended_kind = OFFICIAL_ROUTE_KIND if live and resolver is resolve_antigravity_acp_route_binding else SYNTHETIC_PEER_KIND
    launch_parameters = {
        "entrypoint": "_antigravity_acp_structured_launch",
        "requested_model": EXACT_AGY_MODEL,
        "task_text_bound": True,
        "route_resolver": (
            OFFICIAL_RESOLVER_NAME
            if resolver is resolve_antigravity_acp_route_binding
            else getattr(resolver, "__name__", "substitute")
        ),
        "intended_kind": intended_kind,
        "catalog_injected": False,
        "contract_repo": str(workspace_dir.resolve()),
        "expected_workspace_path": str(workspace_dir.resolve()),
        "effort": None,
        "apply_known_answer": False if live else True,
        "client_callback_policy": {"fs": False, "terminal": False},
        "callback_enablement_from_flags": "not_implemented",
        "first_turn_source": FIRST_TURN_SOURCE,
        "owner_next_turn_is_first_turn": False,
        "product_runtime_timeout_ms": PRODUCT_RUNTIME_TIMEOUT_MS,
        "product_timeout_feature_added": False,
    }

    owner = None
    continuation = None
    launched = None
    second = None
    mapping = None
    models = None
    helper_start = None
    process_observation = None
    second_observation = None
    backend_after_finish = None
    backend_acceptance = None
    finish_attempted = False
    cleanup = None
    fence = None
    primary: Optional[BaseException] = None
    cleanup_error: Optional[BaseException] = None
    runner = None
    used_kind = intended_kind

    def _control_identity() -> Dict[str, Any]:
        return {
            "owner_id": None if continuation is None else continuation.get("owner_id"),
            "continuation_id": None if continuation is None else continuation.get("continuation_id"),
        }

    def _observe(helper: Mapping[str, Any], sampled_after: str) -> Dict[str, Any]:
        return observe_helper_and_backend(
            helper,
            sampled_after=sampled_after,
            os_descendants=inject_os_descendants,
            backend_incarnations=inject_backend_incarnations,
            extra_owned_pids=extra_owned_pids,
        )

    def attempt_owner_finish() -> None:
        nonlocal finish_attempted, cleanup, fence, cleanup_error
        nonlocal backend_after_finish, backend_acceptance
        if finish_attempted or owner is None or continuation is None:
            return
        finish_attempted = True
        if stop_owned_backends is not None:
            try:
                stop_owned_backends()
            except Exception:
                pass
        try:
            closed = finish_owned(owner, continuation)
            cleanup = dict(closed)
            child_exit = dict(closed.get("child_exit") or {})
            incarnations = merge_backend_incarnations(process_observation, second_observation)
            backend_after_finish = evaluate_backend_after_finish(
                incarnations,
                policy=backend_cleanup_policy(live=live, used_kind=used_kind),
            )
            helper_uncertain = evaluate_helper_exit(child_exit)
            backend_uncertain = bool(backend_after_finish.get("cleanup_uncertain"))
            accept_uncertain = None
            try:
                backend_acceptance = accept_unsupported_backend_discard(
                    closed,
                    child_exit,
                    backend_after_finish,
                )
            except ValidationError as exc:
                backend_acceptance = {
                    "accepted": False,
                    "reason": _short(exc),
                    "helper_exit_sufficient": False,
                }
                backend_uncertain = True
                accept_uncertain = _short(exc)
            cleanup["backend_after_finish"] = backend_after_finish
            cleanup["backend_acceptance"] = backend_acceptance
            if helper_uncertain is not None or backend_uncertain:
                if helper_uncertain is not None:
                    reason = helper_uncertain["reason"]
                elif backend_after_finish.get("reason"):
                    reason = backend_after_finish["reason"]
                else:
                    reason = accept_uncertain or "owned backend cleanup is uncertain"
                fence = write_cleanup_fence(
                    fence_dir=owned_state / "fences",
                    session=session_id,
                    reason=reason,
                    helper_pid=child_exit.get("pid"),
                    workspace=workspace_dir,
                    state_root=owned_state,
                    extra={
                        **_control_identity(),
                        "child_exit_exited": child_exit.get("exited"),
                        "backend_after_finish": backend_after_finish,
                        "backend_acceptance": backend_acceptance,
                    },
                )
                cleanup["cleanup_fence"] = fence
        except Exception as exc:
            cleanup_error = exc
            helper_pid = None
            if runner is not None:
                try:
                    helper_pid = runner.runtime.child_process_identity().get("pid")
                except Exception:
                    helper_pid = None
            elif owner is not None and owner.last_child_exit:
                helper_pid = owner.last_child_exit.get("pid")
            fence = write_cleanup_fence(
                fence_dir=owned_state / "fences",
                session=session_id,
                reason="owner.finish raised during driver-owned cleanup",
                helper_pid=helper_pid,
                workspace=workspace_dir,
                state_root=owned_state,
                extra={
                    **_control_identity(),
                    "cleanup_error_type": type(exc).__name__,
                },
            )
            cleanup = {
                "local_release": None,
                "final_discard": None,
                "backend_discard": None,
                "child_exit": dict(owner.last_child_exit or {}),
                "cleanup_fence": fence,
                "backend_after_finish": backend_after_finish,
                "backend_acceptance": backend_acceptance,
            }

    captured_stops, restore_stops = install_turn_stop_reason_capture()
    try:
        launched = launch(
            session=session_id,
            contract=make_contract(workspace_dir),
            transport=bind_run_transport("antigravity-acp"),
            state_root=owned_state,
            requested_model=EXACT_AGY_MODEL,
            prompt=TASK_TEXT,
            route_resolver=resolver,
            catalog=catalog,
        )
        if launched.get("live_antigravity_acp_claimed") is True:
            raise ValidationError("this implementation allocation cannot claim a live PASS")
        if not isinstance(launched.get("owner"), AcpConsumerOwner):
            raise IdentityError("structured launch did not return AcpConsumerOwner")
        contain_bodies(launched["continuation"], label="continuation")
        if TASK_TEXT in str(launched) or FOLLOW_UP_TEXT in str(launched):
            raise ValidationError("launch evidence retained a prompt body")
        owner = launched["owner"]
        continuation = launched["continuation"]
        resolved = owner.resolve(continuation)
        runner = resolved["runner"]
        helper_start = helper_child_identity(owner, continuation)
        if helper_start.get("exited") is True or not isinstance(helper_start.get("pid"), int):
            raise ValidationError("task-owned Node helper start identity is incomplete")
        if inject_unsupported_backend_close:
            def _unsupported_close(_payload: Mapping[str, Any]) -> Dict[str, Any]:
                error = UnsupportedError("Agent does not support session/close")
                error.code = "ACP_BACKEND_UNSUPPORTED_CONTROL"
                raise error

            runner.runtime.close = _unsupported_close
            runner.runtime.local_cleanup_proved = True
        # structured_launch already completed first turn via require_observation.
        process_observation = _observe(helper_start, "structured_launch_first_turn")
        used_kind = helper_start.get("kind") or used_kind
        if retain_owned_runtime is not None:
            retain_owned_runtime["owner"] = owner
            retain_owned_runtime["continuation"] = continuation
            retain_owned_runtime["runner"] = runner
            retain_owned_runtime["runtime"] = runner.runtime
            retain_owned_runtime["original_finish"] = runner.finish
            retain_owned_runtime["original_shutdown"] = runner.runtime.shutdown
        mapping = identity_mapping(continuation)
        models = model_evidence(
            launched,
            live=live,
            catalog_injected=False,
            used_kind=used_kind,
        )
        if inject_post_launch_failure == "raise_cleanup":
            runner.finish = lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("injected cleanup failure"))
            runner.runtime.shutdown = lambda: (_ for _ in ()).throw(RuntimeError("injected cleanup failure"))
            raise RuntimeError("injected post-launch assertion failure")
        if inject_post_launch_failure == "raise_uncertain":
            runtime = runner.runtime
            runtime.shutdown = lambda: None
            runtime.child_process_identity = lambda: {
                "pid": helper_start.get("pid"),
                "returncode": None,
                "exited": False,
                "kind": helper_start.get("kind"),
            }
            raise RuntimeError("injected post-launch assertion failure")
        if inject_post_launch_failure == "raise":
            raise RuntimeError("injected post-launch assertion failure")
        first_request = continuation["request_id"]
        if continue_turn:
            second_request = "%s-turn-2" % continuation["session"]
            second = owner.next_turn(
                continuation,
                text=FOLLOW_UP_TEXT,
                request_id=second_request,
                expected_workspace=workspace_snapshot(workspace_dir),
            )
            contain_bodies(second["continuation"], label="second continuation")
            require_request_match(second["observation"], second_request)
            if second["continuation"]["request_id"] == first_request:
                raise IdentityError("second turn reused the first request identity")
            if second["continuation"]["request_id"] == "%s-turn-1" % continuation["session"]:
                raise IdentityError("owner.next_turn was treated as the first turn")
            if second["continuation"]["session"] != continuation["session"]:
                raise IdentityError("second turn created a new session")
            if TASK_TEXT in str(second) or FOLLOW_UP_TEXT in str(second):
                raise ValidationError("next_turn evidence retained a prompt body")
            helper_after = helper_child_identity(owner, second["continuation"])
            if helper_after.get("pid") != helper_start.get("pid"):
                raise IdentityError("task-owned Node helper identity changed without an observed start")
            second_observation = _observe(helper_after, "owner_next_turn_second_turn")
            continuation = second["continuation"]
        if after_turns is not None:
            after_turns(workspace_dir)
        from puppet_lib.antigravity_acp import AntigravityAcpController

        if AntigravityAcpController.available() or owner.available():
            raise ValidationError("ordinary or default Antigravity ACP availability must stay false")
        attempt_owner_finish()
    except BaseException as exc:
        primary = exc
    finally:
        restore_stops()
        attempt_owner_finish()

    fixture_retained = workspace_dir.is_dir()
    state_retained = owned_state.is_dir()
    injected = inject_post_launch_failure in {"raise", "raise_uncertain", "raise_cleanup"}
    should_apply = apply_known_answer if apply_known_answer is not None else (not live)
    should_inspect = inspect_after if inspect_after is not None else True
    offline_fix = None
    after = None
    fixture_outcome = None
    if live and should_apply:
        helper_error = ValidationError("live mode must never apply_intended_implementation")
        if primary is None:
            primary = helper_error
        should_apply = False
    if should_apply and primary is None:
        implementation = apply_intended_implementation(workspace_dir)
        offline_fix = {
            "implementation_sha256": implementation,
            "implementation_path": "bin/normalize-lines.mjs",
            "offline_known_answer": True,
            "useful_agent_output": False,
            "agy_useful_edit_unproven": True,
            "label": "offline/unproven host-applied known-answer; not live AGY work",
        }
    if should_inspect:
        if live:
            label = "live agent after; no known-answer applied"
        elif should_apply:
            label = "offline/unproven host-applied known-answer; not useful agent output"
        else:
            label = "ordinary no-edit/fixture-after; host known-answer not applied"
        fixture_outcome = collect_fixture_after(
            workspace_dir,
            protected=protected,
            label=label,
            require_implementation=True,
        )
        after = {
            "label": fixture_outcome["label"],
            "tests": fixture_outcome["tests"],
            "check_normalized": fixture_outcome["check_normalized"],
            "check_dirty": fixture_outcome["check_dirty"],
            "protected_digests": fixture_outcome["protected_digests"],
            "changed_paths": fixture_outcome["changed_paths"],
            "agy_useful_edit_unproven": True,
        }
        if not fixture_outcome["ok"] and primary is None:
            primary = ValidationError(
                fixture_outcome["primary_error"] or "fixture after assertion failed"
            )
    if fence is not None and primary is None:
        primary = ValidationError("cleanup uncertain: %s" % fence.get("reason"))
    if cleanup_error is not None and primary is None:
        primary = cleanup_error

    child_exit = dict((cleanup or {}).get("child_exit") or {})
    if not child_exit and owner is not None:
        child_exit = dict(owner.last_child_exit or {})
    first_request_id = None if mapping is None else mapping.get("host", {}).get("request_id")
    if launched is not None and first_request_id is None:
        first_request_id = launched.get("continuation", {}).get("request_id")
    second_request_id = None if second is None else second["continuation"]["request_id"]
    first_stop = captured_stops[0] if captured_stops else UNKNOWN
    second_stop = captured_stops[1] if len(captured_stops) > 1 else UNKNOWN
    turn_attribution = {
        "structured_launch_includes_first_turn": True,
        "require_observation_completes_first_turn": True,
        "owner_next_turn_is_first_turn": False,
        "first_turn_source": FIRST_TURN_SOURCE,
        "second_turn_source": SECOND_TURN_SOURCE if second is not None else None,
        "first_request_id": observed_or_unknown(first_request_id),
        "second_request_id": observed_or_unknown(second_request_id),
        "first_stop_reason": observed_or_unknown(first_stop if launched is not None else None),
        "second_stop_reason": observed_or_unknown(second_stop if second is not None else None),
    }
    same_owner_continuation = UNKNOWN
    if mapping is not None and second is not None:
        same_owner_continuation = (
            second["continuation"]["owner_id"] == mapping.get("owner_id")
            and second["continuation"]["continuation_id"] == mapping.get("continuation_id")
        )
    owner_existed = owner is not None and continuation is not None
    source_ids = incremental_mapping(source_identities)
    artifact_ids = incremental_mapping(artifact_identities)
    if "source_head" not in source_ids:
        source_ids = {"available": False, "value": UNKNOWN, **source_ids}
    if "artifact_sha256" not in artifact_ids:
        artifact_ids = {"available": False, "value": UNKNOWN, **artifact_ids}
    finish_result = cleanup
    if finish_result is None:
        finish_result = {
            "result": UNKNOWN,
            "attempted": finish_attempted,
            "owner_existed": owner_existed,
            "cleanup_fence": fence,
        }
    ok = primary is None and cleanup_error is None and fence is None
    if injected:
        mode = "injected_post_launch_failure"
    elif live and used_kind == OFFICIAL_ROUTE_KIND:
        mode = "live_official_route"
    elif live:
        mode = "live_path_substitute"
    elif fixture_outcome is not None and not fixture_outcome["ok"]:
        mode = "ordinary_fixture_failure"
    else:
        mode = "offline_synthetic"
    destination = (
        Path(receipt_path)
        if receipt_path is not None
        else allocate_fresh_receipt_path(
            Path(receipt_dir) if receipt_dir is not None else owned_state / "receipts"
        )
    )
    evidence = {
        "schema": EVIDENCE_SCHEMA,
        "receipt_schema": RECEIPT_SCHEMA,
        "mode": mode,
        "ok": ok,
        "live": False,
        "live_claimed": False,
        "qualifying_pass": False,
        "injected_failure": bool(injected and primary is not None),
        "primary_preserved": primary is not None,
        "primary_error": None if primary is None else error_label(primary),
        "cleanup_error": None if cleanup_error is None else error_label(cleanup_error),
        "cleanup_failure_visible": cleanup_error is not None or fence is not None,
        "finish_attempted_once": finish_attempted,
        "route_kind": used_kind,
        "test_only": used_kind == SYNTHETIC_PEER_KIND,
        "synthetic_live_pass_possible": False,
        "runtime_contacted": launched is not None,
        "official_agy_provider_contacted": False,
        "synthetic_peer_used": used_kind == SYNTHETIC_PEER_KIND and launched is not None,
        "provider_never_contacted_implied": False,
        "entrypoint": "_antigravity_acp_structured_launch",
        "continuation_api": "owner.next_turn",
        "cleanup_api": "owner.finish",
        "turn_attribution": turn_attribution,
        "turns": {
            "first": {
                "source": FIRST_TURN_SOURCE,
                "request_id": observed_or_unknown(first_request_id),
                "stop_reason": observed_or_unknown(first_stop if launched is not None else None),
            },
            "second": {
                "source": SECOND_TURN_SOURCE if second is not None else UNKNOWN,
                "request_id": observed_or_unknown(second_request_id),
                "stop_reason": observed_or_unknown(second_stop if second is not None else None),
                "same_owner_continuation": same_owner_continuation,
            },
        },
        "launch_parameters": launch_parameters,
        "launch_input": launch_gate,
        "identities": {
            "source": source_ids,
            "artifact": artifact_ids,
            "route": {
                "official_vs_synthetic": "official" if live else "synthetic",
                "kind": used_kind,
                "test_only": used_kind == SYNTHETIC_PEER_KIND,
                "live_pass_possible": False,
                "transport": TRANSPORT_ID,
                "target": TARGET,
                "adapter": ADAPTER_ID,
                "runtime_id": RUNTIME_ID,
                "runtime_version": RUNTIME_VERSION,
                "client_callback_policy": {"fs": False, "terminal": False},
                "callback_enablement_from_flags": "not_implemented",
                "useful_edit_ability": "unproven",
                "default_model": DEFAULT_ANTIGRAVITY_MODEL,
            },
        },
        "owner_id": UNKNOWN if owner is None else owner.owner_id,
        "owner_handle_existed": owner_existed,
        "continuation": mapping if mapping is not None else UNKNOWN,
        "second_request_id": observed_or_unknown(second_request_id),
        "model": models if models is not None else {
            "requested_model": EXACT_AGY_MODEL,
            "advertised_models": UNKNOWN,
            "selected_model": UNKNOWN,
            "current_model": UNKNOWN,
            "selection_state": UNKNOWN,
            "effort": None,
            "source": UNKNOWN,
            "catalog_injected": False,
            "synthetic_model_used_as_live": False,
        },
        "child_start": helper_start,
        "process": {
            "first_turn": process_observation,
            "second_turn": second_observation,
            "backend_after_finish": backend_after_finish,
        },
        "backend_acceptance": backend_acceptance,
        "finish": finish_result,
        "cleanup": {
            "final_discard": None if cleanup is None else cleanup.get("final_discard"),
            "local_release": None if cleanup is None else cleanup.get("local_release"),
            "backend_discard": None if cleanup is None else cleanup.get("backend_discard"),
            "child_exit": child_exit,
            "cleanup_fence": fence,
            "owner_mediated": owner_existed,
            "cleanup_api": "owner.finish",
            "backend_after_finish": backend_after_finish,
            "backend_acceptance": backend_acceptance,
            "uncertain": fence is not None or not owner_existed,
        },
        "workspace": workspace if workspace_dir.is_dir() else UNKNOWN,
        "baseline": {
            "tests": baseline_tests,
            "files": fixture_file_list(workspace_dir) if workspace_dir.is_dir() and not should_apply else None,
            "digests": protected,
            "git": workspace,
            "bin_present": (workspace_dir / "bin" / "normalize-lines.mjs").exists() and not should_apply,
        },
        "after": after,
        "fixture_outcome": fixture_outcome,
        "offline_known_answer": offline_fix,
        "fixture_retained": fixture_retained,
        "state_retained": state_retained,
        "session_replaced": False,
        "task_text_retained": False,
        "response_retained": False,
        "implementation_job_id": IMPLEMENTATION_JOB_ID,
        "owner_task_id": OWNER_TASK_ID,
        "receipt": {
            "path": str(destination.resolve()),
            "fresh_destination": True,
            "schema": RECEIPT_SCHEMA,
            "overwrote": False,
        },
    }
    if TASK_TEXT in str(evidence) or FOLLOW_UP_TEXT in str(evidence):
        raise ValidationError("receipt retained a prompt body")
    persisted = persist_receipt(destination, evidence)
    evidence["receipt"]["sha256"] = persisted["sha256"]
    label = "injected failure evidence" if injected else "lifecycle evidence"
    return body_free(evidence, label=label)


def run_fixture_baseline() -> Dict[str, Any]:
    workspace = V4_ROOT / "workspaces" / "fixture-baseline"
    snapshot = create_fixture_workspace(workspace)
    result = run_node_test(workspace)
    if result["pass_count"] != 1 or result["fail_count"] != 1 or result["exit_code"] == 0:
        raise ValidationError("fixture baseline must be exactly one pass and one missing --check failure")
    evidence = {
        "phase": "baseline",
        "files": fixture_file_list(workspace),
        "digests": fixture_digests(workspace),
        "git": snapshot,
        "tests": result,
        "bin_present": (workspace / "bin" / "normalize-lines.mjs").exists(),
        "offline_unproven": True,
    }
    return body_free(evidence, label="fixture baseline")


def run_fixture_after() -> Dict[str, Any]:
    workspace = V4_ROOT / "workspaces" / "fixture-after"
    snapshot = create_fixture_workspace(workspace)
    protected = fixture_digests(workspace)
    implementation = apply_intended_implementation(workspace)
    after = inspect_fixture_after(
        workspace,
        protected=protected,
        label="offline/unproven host-applied known-answer; not useful agent output",
        require_implementation=True,
    )
    evidence = {
        "phase": "after",
        "files": fixture_file_list(workspace),
        "protected_digests": after["protected_digests"],
        "implementation_sha256": implementation,
        "implementation_path": "bin/normalize-lines.mjs",
        "changed_paths": after["changed_paths"],
        "git_baseline": snapshot,
        "git_after_status": git(workspace, "status", "--porcelain=v1"),
        "git_after_diff_stat": git(workspace, "diff", "--stat", "--", "bin/normalize-lines.mjs"),
        "tests": after["tests"],
        "check_normalized": after["check_normalized"],
        "check_dirty": after["check_dirty"],
        "useful_edit_by": "host_independent_after",
        "agy_useful_edit_unproven": True,
        "label": "offline/unproven host-applied known-answer",
    }
    return body_free(evidence, label="fixture after")


def emit(value: Mapping[str, Any]) -> int:
    print(json.dumps(value, indent=2, sort_keys=True))
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="v4 Antigravity ACP failure-receipt proof driver")
    parser.add_argument(
        "--mode",
        default="lifecycle",
        choices=(
            "lifecycle",
            "ordinary-fixture-failure",
            "fixture-baseline",
            "fixture-after",
            "reject-live",
            "stage-live",
        ),
    )
    parser.add_argument("--live", action="store_true", help="official route; requires --launch-input")
    parser.add_argument("--launch-input", default=None, help="parent-supplied validated launch-input file")
    args = parser.parse_args(argv)
    try:
        if args.mode == "stage-live":
            return emit({"ok": True, "staged": write_staged_artifacts(), "executed": False, "live": False})
        if args.mode == "reject-live":
            reject_live_claim(live=True)
        if args.live and args.mode not in {"lifecycle"}:
            raise ValidationError("official live path is selected only with --mode lifecycle")
        if args.mode == "lifecycle" and args.live:
            gate = require_launch_input(Path(args.launch_input) if args.launch_input else None)
            evidence = consume(
                live=True,
                launch_input=Path(gate["path"]),
                receipt_dir=V4_ROOT / "receipts",
            )
            emit(evidence)
            return 0 if evidence.get("ok") else 2
        if args.live:
            require_launch_input(Path(args.launch_input) if args.launch_input else None)
        if args.mode == "ordinary-fixture-failure":
            evidence = consume(
                live=False,
                apply_known_answer=False,
                inspect_after=True,
                receipt_dir=V4_ROOT / "receipts",
            )
            emit(evidence)
            return 0 if evidence.get("ok") else 2
        if args.mode == "lifecycle":
            evidence = consume(live=False, receipt_dir=V4_ROOT / "receipts")
            emit(evidence)
            return 0 if evidence.get("ok") else 2
        if args.mode == "fixture-baseline":
            return emit(run_fixture_baseline())
        if args.mode == "fixture-after":
            return emit(run_fixture_after())
        raise ValidationError("unsupported v4 driver mode")
    except (IdentityError, UnsupportedError, ValidationError, CleanupVisibleError) as exc:
        payload = {
            "ok": False,
            "error_type": type(exc).__name__,
            "blocker": str(exc),
            "live": False,
        }
        if isinstance(exc, CleanupVisibleError):
            payload["primary_error"] = error_label(exc.primary)
            payload["cleanup_error"] = error_label(exc.cleanup)
            payload["cleanup_fence"] = exc.fence
        contain_bodies(payload, label="driver error")
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 2


if __name__ == "__main__":
    sys.exit(main())
