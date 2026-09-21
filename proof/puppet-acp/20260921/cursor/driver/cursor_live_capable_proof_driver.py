#!/usr/bin/env python3
"""Cursor v3 live-capable proof driver through _cursor_acp_structured_launch.

Default invocation is offline and does not start a provider. An explicit
--live plus a parent-issued non-secret --parent-release and a fresh
--session can select the already-implemented official-route path. Missing
release or a reused session path rejects before any process starts.
Product source is not modified. Ordinary available() stays false. This
driver does not claim a live PASS from synthetic substitutes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Dict, Mapping, Optional


DRIVER_FILE = Path(__file__).resolve()
V3_ROOT = DRIVER_FILE.parents[1]
V2_ROOT = V3_ROOT.parent / "v2"
V1_ROOT = V3_ROOT.parent
WORKTREE = DRIVER_FILE.parents[5]
SCRIPTS = WORKTREE / "skills" / "puppet" / "scripts"
TEMPLATE_DIR = V3_ROOT / "fixture"
TEMPLATE_IMPL = TEMPLATE_DIR / "normalize-lines.mjs"
TEMPLATE_TEST = TEMPLATE_DIR / "normalize-lines.test.mjs"
PIN_ARTIFACT = (
    WORKTREE
    / "runs"
    / "puppet-dual-acp-controller-runs"
    / "20260921"
    / "artifacts-refresh-2e05de52"
    / "acpx-0.18.0.tgz"
)
RUNTIME_ROOT = (
    WORKTREE
    / "runs"
    / "puppet-dual-acp-controller-runs"
    / "20260921"
    / "runtime-refresh-2e05de52"
)

EXPECTED_ARTIFACT_SHA256 = "5df327172d83644b5f44925386095c8facce28eb78d1ea81f243d7b100d6e614"
EXPECTED_UPSTREAM_COMMIT = "2e05de525dd1ab62e9e74bf02d91e3638920fcf3"
EXPECTED_UPSTREAM_TREE = "c612e764ead5d8eaa409956fb1b11c008a7579ed"
EXPECTED_SOURCE_HEAD = "d5e33f67f6b42384f6feec1d15be3b69b4525eb8"
EXPECTED_SOURCE_TREE = "938ef948a6a1218ad055a17d5d297c633b936167"
EXPECTED_PROTECTED_TEST_SHA256 = (
    "bf063a0bdbf43dbe3fcda4e4d297af1aebcc2d7d1766efb6582f38e84710742e"
)
EXPECTED_IMPORTS = {
    "package/dist/runtime.js": "ffdb6949b2239d991f63970514ad99677b19db1839313127a55ad9fcd30a4683",
    "package/dist/agent-registry-Ct2yWPW7.js": (
        "5091abb775cb9cfc36bc210acd84a830bd5a413db2ba61eab8a0ef22817230ba"
    ),
    "package/dist/ipc-Bn8rocUR.js": (
        "33b50f531ae5bb3d39a56b9f325249631721aee54c764b1ce5a2f72a1eff98c0"
    ),
    "package/dist/queue-owner-runtime-B-uQhwMC.js": (
        "fc4f3b27e6c003646539fc933a38c80886e1cdabf38d6f33a4abc7185d8b0d5b"
    ),
    "package/dist/watch-yKB9yCio.js": (
        "06254f5cf0af1ee1b5855c0380469ea5f6b691d7f693cfa519288adb7798c635"
    ),
}

# OFFLINE-ONLY known-answer. Live mode must never write this after launch.
FIXED_IMPL = """\
/**
 * Disposable proof fixture. Intentionally broken baseline:
 * CRLF becomes LF, but lone CR is left unchanged.
 * A later worker may fix only this file. Do not edit the tests.
 */
export function normalizeLines(text) {
  return String(text).replace(/\\r\\n?/g, "\\n");
}
"""

FIRST_TASK_TEXT = (
    "In this disposable proof fixture, inspect the failing lone-CR "
    "normalizeLines case, make the minimal implementation-only fix in "
    "normalize-lines.mjs, run node --test normalize-lines.test.mjs, then stop. "
    "Do not edit the protected test file, install packages, access the network, "
    "alter credentials, or change product source."
)
SECOND_TASK_TEXT = (
    "Verify the lone-CR normalizeLines fix in this same owned session and stop. "
    "Do not edit files."
)
PLACEHOLDER_TASK_TEXT = "cursor-acp-runtime-turn"

LIVE_SELECTOR = "cursor-grok-4.6-high"
LIVE_CURRENT_MODEL = "grok-4.6[effort=high,fast=true]"
OFFICIAL_ROUTE_IDENTITY = "cursor-agent-acp"
OFFICIAL_RESOLVER_NAME = "resolve_cursor_acp_route_binding"
FIXTURE_BRANCH = "cursor-proof-fixture-v3"
SYNTHETIC_MODELS = {
    "currentModelId": "candidate-default",
    "availableModelIds": ["candidate-default", "candidate-fast"],
}
SYNTHETIC_REQUESTED = "candidate-fast"
IMPLEMENTATION_JOB_ID = "91a1240f-de3d-4546-a809-3a68c54d13d0"
LIVE_RELEASE_MISSING = (
    "live Cursor provider qualification requires --live plus a parent-issued "
    "non-secret --parent-release; missing release rejects before process start"
)
LIVE_SESSION_REQUIRED = (
    "live invocation requires an explicit fresh --session; default live "
    "session is refused"
)
LIVE_PATH_EXISTS = (
    "live workspace, state, or fence already exists; existing evidence is "
    "preserved and retry is refused"
)
LIVE_NOT_RELEASED = (
    "live Cursor provider qualification is default-off and is not released"
)
PARENT_RELEASE_ENV = "PUPPET_CURSOR_PROOF_PARENT_RELEASE"
STAGED_PARENT_RELEASE = "PARENT_ISSUED_RELEASE"
STAGED_LIVE_SESSION = "cursor-proof-v3-live-20260921-oneshot"
BACKEND_EXECUTABLE_NAME = "cursor-agent"
FIRST_TURN_SOURCE = "_cursor_acp_structured_launch.require_observation"
SECOND_TURN_SOURCE = "owner.next_turn"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _error_label(exc: BaseException) -> Dict[str, str]:
    return {
        "type": type(exc).__name__,
        "message": str(exc).split("\n", 1)[0][:240],
    }


def parent_release_value(explicit: Optional[str] = None) -> Optional[str]:
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    env = os.environ.get(PARENT_RELEASE_ENV)
    if isinstance(env, str) and env.strip():
        return env.strip()
    return None


def require_parent_release(release: Optional[str]) -> str:
    """Reject a live request before any consumer process starts."""

    value = parent_release_value(release)
    if value is None:
        raise RuntimeError(LIVE_RELEASE_MISSING)
    return value


def require_explicit_live_session(session: Optional[str]) -> str:
    if not isinstance(session, str) or not session.strip():
        raise RuntimeError(LIVE_SESSION_REQUIRED)
    return session.strip()


def reject_live_without_release(live: bool, release: Optional[str] = None) -> None:
    env_live = os.environ.get("PUPPET_CURSOR_PROOF_LIVE") == "1"
    if not live and not env_live:
        return
    require_parent_release(release)


def live_owned_paths(
    *,
    session: str,
    state_root: Optional[Path] = None,
    fixture_dir: Optional[Path] = None,
) -> Dict[str, Path]:
    workspace = Path(fixture_dir) if fixture_dir is not None else V3_ROOT / "workspaces" / session
    state = Path(state_root) if state_root is not None else V3_ROOT / "state" / session
    fence_dir = (
        Path(state_root) / "fences" / session
        if state_root is not None
        else V3_ROOT / "fences" / session
    )
    return {
        "workspace": workspace,
        "state": state,
        "fence_dir": fence_dir,
        "fence": fence_dir / ("%s-cleanup-uncertain.json" % session),
    }


def reject_existing_live_session_paths(paths: Mapping[str, Path]) -> None:
    existing = []
    if paths["workspace"].exists():
        existing.append("workspace")
    if paths["state"].exists():
        existing.append("state")
    fence_dir = paths["fence_dir"]
    if paths["fence"].exists() or (
        fence_dir.exists() and any(fence_dir.iterdir())
    ):
        existing.append("fence")
    if existing:
        raise RuntimeError("%s (%s)" % (LIVE_PATH_EXISTS, ", ".join(existing)))


def _source_git(args: list[str]) -> str:
    return subprocess.check_output(
        ["git", *args],
        cwd=str(WORKTREE),
        text=True,
    ).strip()


def _fixture_git(repo: Path, args: list[str], *, env: Optional[Mapping[str, str]] = None) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        capture_output=True,
        check=False,
        env=None if env is None else dict(env),
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "fixture git failed: %s" % (completed.stderr or completed.stdout or args)
        )
    return completed.stdout.strip()


def source_identity() -> Dict[str, Any]:
    return {
        "path": str(WORKTREE),
        "branch": _source_git(["branch", "--show-current"]),
        "head": _source_git(["rev-parse", "HEAD"]),
        "tree": _source_git(["rev-parse", "HEAD^{tree}"]),
        "dirty": bool(_source_git(["status", "--porcelain=v1"])),
        "expected_head": EXPECTED_SOURCE_HEAD,
        "expected_tree": EXPECTED_SOURCE_TREE,
        "immutable_parent": "b8672726939a64710c69f4c2839b037d15e36945",
        "product_source_altered": False,
        "upstream_commit": EXPECTED_UPSTREAM_COMMIT,
        "upstream_tree": EXPECTED_UPSTREAM_TREE,
    }


def fixture_identity(repo: Path) -> Dict[str, Any]:
    return {
        "path": str(Path(repo).resolve()),
        "branch": _fixture_git(repo, ["branch", "--show-current"]),
        "head": _fixture_git(repo, ["rev-parse", "HEAD"]),
        "tree": _fixture_git(repo, ["rev-parse", "HEAD^{tree}"]),
        "dirty": bool(_fixture_git(repo, ["status", "--porcelain=v1"])),
    }


def require_attached_branch(identity: Mapping[str, Any]) -> str:
    branch = identity.get("branch")
    if not isinstance(branch, str) or not branch.strip():
        raise RuntimeError(
            "fixture workspace is detached; launch refused rather than fabricating a branch"
        )
    if branch != FIXTURE_BRANCH:
        raise RuntimeError("fixture workspace branch is not %s" % FIXTURE_BRANCH)
    return branch


def verify_existing_runtime() -> Dict[str, Any]:
    """Reuse the already-verified task-local materialization. No rebuild."""

    if not PIN_ARTIFACT.is_file():
        raise FileNotFoundError("pinned acpx artifact is missing")
    pin_digest = sha256_file(PIN_ARTIFACT)
    if pin_digest != EXPECTED_ARTIFACT_SHA256:
        raise RuntimeError("pinned acpx artifact digest mismatch")
    module_path = RUNTIME_ROOT / "node_modules" / "acpx" / "dist" / "runtime.js"
    if not module_path.is_file() or module_path.is_symlink():
        raise RuntimeError("materialized runtime module is missing; rebuild is refused")
    imports = {}
    for relative, expected in EXPECTED_IMPORTS.items():
        installed = RUNTIME_ROOT / "node_modules" / "acpx" / relative.split("package/", 1)[1]
        digest = sha256_file(installed)
        if digest != expected:
            raise RuntimeError("runtime import digest drifted: %s" % relative)
        imports[relative] = digest
    return {
        "artifact": {
            "pin_path": str(PIN_ARTIFACT),
            "sha256": pin_digest,
        },
        "runtime_root": str(RUNTIME_ROOT),
        "module_path": str(module_path),
        "module_sha256": imports["package/dist/runtime.js"],
        "imported_chunks": imports,
        "lifecycle_scripts": "disabled",
        "reused": True,
        "rebuilt": False,
        "merge_commit": EXPECTED_UPSTREAM_COMMIT,
    }


def create_fixture_workspace(dest: Path) -> Dict[str, Any]:
    dest = Path(dest)
    if dest.exists() and any(dest.iterdir()):
        raise RuntimeError("fixture workspace destination is not empty")
    dest.mkdir(parents=True, exist_ok=True)
    if not TEMPLATE_IMPL.is_file() or not TEMPLATE_TEST.is_file():
        raise FileNotFoundError("v3 fixture templates are missing")
    if sha256_file(TEMPLATE_TEST) != EXPECTED_PROTECTED_TEST_SHA256:
        raise RuntimeError("protected test template digest mismatch")
    completed = subprocess.run(
        ["git", "init", "-b", FIXTURE_BRANCH],
        cwd=str(dest),
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError("fixture git init failed: %s" % (completed.stderr or completed.stdout))
    shutil.copy2(TEMPLATE_IMPL, dest / "normalize-lines.mjs")
    shutil.copy2(TEMPLATE_TEST, dest / "normalize-lines.test.mjs")
    _fixture_git(dest, ["add", "normalize-lines.mjs", "normalize-lines.test.mjs"])
    commit_env = dict(os.environ)
    commit_env.update(
        {
            "GIT_AUTHOR_NAME": "cursor-proof-fixture",
            "GIT_AUTHOR_EMAIL": "cursor-proof-fixture@local",
            "GIT_COMMITTER_NAME": "cursor-proof-fixture",
            "GIT_COMMITTER_EMAIL": "cursor-proof-fixture@local",
        }
    )
    _fixture_git(
        dest,
        ["commit", "-m", "baseline 2 pass / 1 fail"],
        env=commit_env,
    )
    identity = fixture_identity(dest)
    require_attached_branch(identity)
    return identity


def run_fixture_tests(fixture_dir: Path) -> Dict[str, Any]:
    completed = subprocess.run(
        ["node", "--test", "--test-reporter=tap", "normalize-lines.test.mjs"],
        cwd=str(fixture_dir),
        text=True,
        capture_output=True,
        check=False,
    )
    output = "%s\n%s" % (completed.stdout, completed.stderr)
    passed = len(re.findall(r"^ok \d+", output, flags=re.M))
    failed = len(re.findall(r"^not ok \d+", output, flags=re.M))
    return {
        "command": ["node", "--test", "--test-reporter=tap", "normalize-lines.test.mjs"],
        "cwd": str(fixture_dir),
        "returncode": completed.returncode,
        "passed": passed,
        "failed": failed,
        "total": passed + failed,
        "protected_test_sha256": sha256_file(fixture_dir / "normalize-lines.test.mjs"),
        "implementation_sha256": sha256_file(fixture_dir / "normalize-lines.mjs"),
    }


def capture_baseline(fixture_dir: Path) -> Dict[str, Any]:
    baseline = run_fixture_tests(fixture_dir)
    if not (
        baseline["passed"] == 2
        and baseline["failed"] == 1
        and baseline["returncode"] != 0
    ):
        raise RuntimeError("fixture baseline must be 2 passing / 1 failing")
    if baseline["protected_test_sha256"] != EXPECTED_PROTECTED_TEST_SHA256:
        raise RuntimeError("protected test digest mismatch before launch")
    return baseline


def apply_offline_only_known_answer_fix(fixture_dir: Path) -> Dict[str, str]:
    """OFFLINE-ONLY known-answer normalization. Not useful agent output."""

    test_path = Path(fixture_dir) / "normalize-lines.test.mjs"
    impl_path = Path(fixture_dir) / "normalize-lines.mjs"
    before_test = sha256_file(test_path)
    impl_path.write_text(FIXED_IMPL)
    after_test = sha256_file(test_path)
    if before_test != after_test:
        raise RuntimeError("protected test digest changed")
    return {
        "implementation_sha256": sha256_file(impl_path),
        "protected_test_sha256": after_test,
        "implementation_only": True,
        "offline_known_answer": True,
        "useful_agent_output": False,
        "label": "offline-only known-answer normalization; not live agent output",
    }


def inspect_fixture_after(
    fixture_dir: Path,
    *,
    protected_digest: str,
    require_three: bool,
    label: str,
    baseline_implementation_sha256: Optional[str] = None,
) -> Dict[str, Any]:
    names = [
        name
        for name in _fixture_git(fixture_dir, ["diff", "--name-only", "HEAD"]).splitlines()
        if name
    ]
    unrelated = [name for name in names if name != "normalize-lines.mjs"]
    if unrelated:
        raise RuntimeError("unrelated fixture edits: %s" % ", ".join(unrelated))
    after = run_fixture_tests(fixture_dir)
    if after["protected_test_sha256"] != protected_digest:
        raise RuntimeError("protected test digest changed")
    if require_three and not (
        after["passed"] == 3 and after["failed"] == 0 and after["returncode"] == 0
    ):
        raise RuntimeError("fixture after must be 3/3")
    payload = {
        "label": label,
        "tests": after,
        "diff_names": names,
        "unrelated_edits": unrelated,
        "protected_test_digest_unchanged": True,
        "protected_test_path": "normalize-lines.test.mjs",
        "implementation_path": "normalize-lines.mjs",
        "compared_to_fixed_impl": False,
        "known_answer_applied": False,
    }
    if baseline_implementation_sha256 is not None:
        payload["baseline_implementation_sha256"] = baseline_implementation_sha256
        payload["after_implementation_sha256"] = after["implementation_sha256"]
        payload["implementation_changed"] = (
            baseline_implementation_sha256 != after["implementation_sha256"]
        )
    return payload


def synthetic_catalog() -> Dict[str, Any]:
    from puppet_lib.cursor_acp import advertised_catalog_from_runtime_models

    return advertised_catalog_from_runtime_models(SYNTHETIC_MODELS)


def make_contract(*, repo: Path, requested_model: str) -> SimpleNamespace:
    contract = SimpleNamespace()
    contract.repo = Path(repo)
    contract.requested_model = requested_model
    contract.target = "cursor"
    contract.controller = "puppet-owner"
    return contract


def official_route_resolver() -> Any:
    from puppet_lib.cursor_acp import resolve_cursor_acp_route_binding

    return resolve_cursor_acp_route_binding()


def _bind_scripts() -> Any:
    from puppet_lib.acp_consumer import reject_consumer_bodies
    from puppet_lib.cursor_acp import (
        resolve_cursor_acp_route_binding,
        test_only_cursor_synthetic_route_binding,
    )
    from puppet_lib.session import _cursor_acp_structured_launch
    from puppet_lib.transport import bind_run_transport

    return (
        _cursor_acp_structured_launch,
        resolve_cursor_acp_route_binding,
        test_only_cursor_synthetic_route_binding,
        bind_run_transport,
        reject_consumer_bodies,
    )


def _public_ids(continuation: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "schema": continuation.get("schema"),
        "owner_id": continuation.get("owner_id"),
        "continuation_id": continuation.get("continuation_id"),
        "route": continuation.get("route"),
        "session": continuation.get("session"),
        "host_conversation_id": continuation.get("host_conversation_id"),
        "request_id": continuation.get("request_id"),
        "runtime_session_name": continuation.get("runtime_session_name"),
        "backend_session_id": continuation.get("backend_session_id"),
        "acpx_record_id": continuation.get("acpx_record_id"),
        "process_local": continuation.get("process_local"),
        "cross_process_resume": continuation.get("cross_process_resume"),
    }


def _distinct_identities(continuation: Mapping[str, Any]) -> None:
    required = (
        "session",
        "host_conversation_id",
        "request_id",
        "runtime_session_name",
        "backend_session_id",
        "acpx_record_id",
    )
    missing = [key for key in required if not continuation.get(key)]
    if missing:
        raise RuntimeError("host or runtime identity is missing: %s" % ", ".join(missing))
    host_conversation = continuation["host_conversation_id"]
    request_id = continuation["request_id"]
    runtime_name = continuation["runtime_session_name"]
    backend = continuation["backend_session_id"]
    record = continuation["acpx_record_id"]
    if request_id == backend or request_id == record or request_id == runtime_name:
        raise RuntimeError("host request id is conflated with a runtime identity")
    if host_conversation in {runtime_name, backend, record}:
        raise RuntimeError("host conversation is conflated with a runtime identity")


def _event_summary(runner: Any) -> Dict[str, Any]:
    discarded = getattr(runner, "discarded_events", None) or {}
    return {
        "event_count": discarded.get("event_count"),
        "observed_types": list(discarded.get("observed_types") or []),
        "body_retained": discarded.get("body_retained"),
    }


def _identity_fields(identity: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "pid": identity.get("pid"),
        "ppid": identity.get("ppid"),
        "executable_name": identity.get("executable_name"),
        "start_identity": identity.get("start_identity"),
    }


def _ps_identity(pid: int) -> Optional[Dict[str, Any]]:
    """Bounded read-only OS metadata: PID, PPID, executable name, start identity."""

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
    return {
        "pid": int(parts[0]),
        "ppid": int(parts[1]),
        "executable_name": parts[2],
        "start_identity": start.stdout.strip() if start.returncode == 0 else None,
    }


def _owned_helper_children(helper_pid: int) -> list[Dict[str, Any]]:
    """Children of the owned helper only. No broad process scan."""

    completed = subprocess.run(
        ["pgrep", "-P", str(helper_pid)],
        text=True,
        capture_output=True,
        check=False,
        timeout=5,
    )
    if completed.returncode != 0 or not completed.stdout.strip():
        return []
    children = []
    for token in completed.stdout.split():
        try:
            pid = int(token)
        except ValueError:
            continue
        identity = _ps_identity(pid)
        if identity is not None:
            children.append(identity)
    return children


def _backend_name(identity: Mapping[str, Any]) -> str:
    return str(identity.get("executable_name") or "").rsplit("/", 1)[-1]


def observe_helper_and_backend(
    helper_identity: Mapping[str, Any],
    *,
    sampled_after: str,
    os_children: Optional[list[Mapping[str, Any]]] = None,
    backend_incarnations: Optional[list[Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    """Label the Node helper PID separately from matched backend child metadata."""

    helper_pid = helper_identity.get("pid")
    helper_os = _ps_identity(int(helper_pid)) if isinstance(helper_pid, int) else None
    if os_children is None:
        children = _owned_helper_children(int(helper_pid)) if isinstance(helper_pid, int) else []
    else:
        children = [_identity_fields(child) for child in os_children]
    if backend_incarnations is None:
        matched = [
            _identity_fields(child)
            for child in children
            if _backend_name(child) == BACKEND_EXECUTABLE_NAME
        ]
    else:
        matched = [_identity_fields(item) for item in backend_incarnations]
    observed_backend = bool(matched)
    if observed_backend:
        gap = None
    elif children:
        gap = (
            "OS children of the owned helper were not cursor-agent; those PIDs "
            "are helper-side runtime/peer processes, not a Cursor backend. "
            "Backend death is not inferred from helper exit"
        )
    else:
        gap = (
            "no OS child of the owned helper was observed; backend death is "
            "not inferred from helper exit"
        )
    return {
        "sampled_after": sampled_after,
        "first_turn_source": FIRST_TURN_SOURCE,
        "owner_next_turn_is_first_turn": False,
        "helper": {
            "role": "implementation_or_helper",
            "source": "runtime.child_process_identity",
            "note": (
                "Node controller-runtime-driver PID; not automatically a Cursor backend PID"
            ),
            "pid": helper_pid,
            "returncode": helper_identity.get("returncode"),
            "exited": helper_identity.get("exited"),
            "kind": helper_identity.get("kind"),
        },
        "os_helper": helper_os,
        "os_children": children,
        "backend": {
            "observed": observed_backend,
            "child_count": len(matched),
            "incarnations": matched,
            "inferred_from_helper_exit": False,
            "helper_exit_sufficient": False,
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
                item.get("start_identity"),
            )
            if key in seen:
                continue
            seen.add(key)
            merged.append(_identity_fields(item))
    return merged


def pid_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def evaluate_child_exit(child_exit: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    if child_exit.get("exited") is not True:
        return {
            "cleanup_uncertain": True,
            "replacement_blocked": True,
            "reason": "owned helper exit was not proven",
        }
    pid = child_exit.get("pid")
    if not isinstance(pid, int):
        return None
    if pid_is_alive(pid):
        return {
            "cleanup_uncertain": True,
            "replacement_blocked": True,
            "reason": "owned helper pid is still alive",
        }
    return None


def evaluate_backend_after_finish(
    incarnations: list[Mapping[str, Any]],
    *,
    live: bool,
    cleanup: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    contract = source_cleanup_contract(cleanup)
    if contract is not None:
        lifecycle = contract["process_lifecycle"]
        worker = contract.get("worker")
        started = lifecycle.get("started") if isinstance(lifecycle, Mapping) else None
        exits = lifecycle.get("exits") if isinstance(lifecycle, Mapping) else None
        worker_proven = contract.get("worker_termination") == "proven"
        worker_matches = (
            isinstance(worker, Mapping)
            and isinstance(started, list)
            and isinstance(exits, list)
            and any(source_process_identities_match(worker, item) for item in started)
            and any(source_process_identities_match(worker, item) for item in exits)
        )
        if (
            worker_proven
            and worker_matches
            and contract.get("cleanup_uncertain") is False
            and contract.get("replacement_blocked") is False
        ):
            return {
                "matched": True,
                "terminated": True,
                "surviving_pids": [],
                "inferred_from_helper_exit": False,
                "helper_exit_sufficient": False,
                "backend_discard": contract.get("backend_discard"),
                "worker_termination": "proven",
                "process_lifecycle": lifecycle,
                "cleanup_uncertain": False,
                "replacement_blocked": False,
            }
        if live or contract.get("cleanup_uncertain") is True:
            return {
                "matched": bool(started),
                "terminated": False,
                "surviving_pids": [],
                "inferred_from_helper_exit": False,
                "helper_exit_sufficient": False,
                "backend_discard": contract.get("backend_discard"),
                "worker_termination": contract.get("worker_termination", "unknown"),
                "process_lifecycle": lifecycle,
                "cleanup_uncertain": True,
                "replacement_blocked": True,
                "reason": "source cleanup contract did not prove exact owned worker termination",
            }
    surviving = []
    for item in incarnations:
        pid = item.get("pid")
        if isinstance(pid, int) and pid_is_alive(pid):
            surviving.append(pid)
    if not incarnations:
        result = {
            "matched": False,
            "terminated": False,
            "surviving_pids": [],
            "inferred_from_helper_exit": False,
            "helper_exit_sufficient": False,
        }
        if live:
            result.update(
                {
                    "cleanup_uncertain": True,
                    "replacement_blocked": True,
                    "reason": (
                        "backend incarnation was not observed after task "
                        "completion; helper exit is not backend proof"
                    ),
                }
            )
        else:
            result["evidence_gap"] = (
                "no matched backend incarnation; helper exit is not backend proof"
            )
        return result
    if surviving:
        return {
            "matched": True,
            "terminated": False,
            "surviving_pids": surviving,
            "inferred_from_helper_exit": False,
            "helper_exit_sufficient": False,
            "cleanup_uncertain": True,
            "replacement_blocked": True,
            "reason": "matched backend incarnation survived owner.finish",
        }
    return {
        "matched": True,
        "terminated": True,
        "surviving_pids": [],
        "inferred_from_helper_exit": False,
        "helper_exit_sufficient": False,
        "cleanup_uncertain": False,
        "replacement_blocked": False,
    }


def source_process_identities_match(left: Any, right: Any) -> bool:
    if not isinstance(left, Mapping) or not isinstance(right, Mapping):
        return False
    if left.get("pid") != right.get("pid"):
        return False
    if not isinstance(left.get("pid"), int) or isinstance(left.get("pid"), bool):
        return False
    if not left.get("launchId") or left.get("launchId") != right.get("launchId"):
        return False
    if not left.get("startedAt") or left.get("startedAt") != right.get("startedAt"):
        return False
    left_scope = left.get("scope")
    right_scope = right.get("scope")
    if not isinstance(left_scope, Mapping) or not isinstance(right_scope, Mapping):
        return False
    if left_scope.get("kind") != right_scope.get("kind"):
        return False
    if left_scope.get("kind") == "runtime-session":
        return left_scope.get("sessionKey") == right_scope.get("sessionKey")
    if left_scope.get("kind") == "runtime-probe":
        return left_scope.get("agent") == right_scope.get("agent")
    return left_scope.get("kind") == "client"


def source_cleanup_contract(cleanup: Optional[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(cleanup, Mapping):
        return None
    nested = cleanup.get("cleanup")
    values: Dict[str, Any] = {}
    if isinstance(nested, Mapping):
        values.update(nested)
    values.update(cleanup)
    required = {"worker_termination", "process_lifecycle"}
    if not required.intersection(values):
        return None
    lifecycle = values.get("process_lifecycle")
    if not isinstance(lifecycle, Mapping):
        lifecycle = {"started": [], "exits": []}
    return {
        "backend_discard": values.get("backend_discard")
        or values.get("backendSessionDiscard"),
        "worker_termination": values.get("worker_termination", "unknown"),
        "cleanup_uncertain": values.get("cleanup_uncertain"),
        "replacement_blocked": values.get("replacement_blocked"),
        "worker": values.get("worker"),
        "process_lifecycle": {
            "started": [item for item in lifecycle.get("started", []) if isinstance(item, Mapping)],
            "exits": [item for item in lifecycle.get("exits", []) if isinstance(item, Mapping)],
        },
    }


def write_cleanup_fence(
    *,
    fence_dir: Path,
    session: str,
    reason: str,
    helper_pid: Any,
    fixture_dir: Path,
    state_root: Path,
    extra: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    fence_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "puppet.cursor-live-capable-cleanup-fence/v3",
        "cleanup_uncertain": True,
        "replacement_blocked": True,
        "session_replaced": False,
        "fixture_deleted": False,
        "state_deleted": False,
        "session": session,
        "reason": reason,
        "helper_pid": helper_pid,
        "fixture_dir": str(fixture_dir),
        "state_root": str(state_root),
        "owner_finish_only": True,
        "helper_exit_sufficient": False,
    }
    if extra:
        payload.update(dict(extra))
    from puppet_lib.acp_consumer import reject_consumer_bodies

    reject_consumer_bodies(payload, label="cleanup fence")
    path = fence_dir / ("%s-cleanup-uncertain.json" % session)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    payload["path"] = str(path)
    payload["sha256"] = sha256_file(path)
    return payload


def staged_live_preflight(session: str) -> Dict[str, Any]:
    paths = live_owned_paths(session=session)
    return {
        "session": session,
        "workspace": str(paths["workspace"]),
        "state": str(paths["state"]),
        "fence": str(paths["fence"]),
        "workspace_exists": paths["workspace"].exists(),
        "state_exists": paths["state"].exists(),
        "fence_exists": paths["fence"].exists(),
        "exclusive": True,
        "retry": False,
        "rmtree_on_live": False,
    }


def staged_live_invocation() -> Dict[str, Any]:
    command = [
        sys.executable,
        str(DRIVER_FILE),
        "--live",
        "--parent-release",
        STAGED_PARENT_RELEASE,
        "--session",
        STAGED_LIVE_SESSION,
    ]
    preflight = staged_live_preflight(STAGED_LIVE_SESSION)
    return {
        "executed": False,
        "command": command,
        "cwd": str(WORKTREE),
        "session": STAGED_LIVE_SESSION,
        "preflight": preflight,
        "selector": LIVE_SELECTOR,
        "expected_current_model": LIVE_CURRENT_MODEL,
        "route_resolver": OFFICIAL_RESOLVER_NAME,
        "official_route_identity": OFFICIAL_ROUTE_IDENTITY,
        "official_executable": "/Users/bobbybones/.local/bin/cursor-agent",
        "argv_tail": "acp",
        "parent_live_allocation": "one session, at most 2 prompts <=300000ms each, no retry",
        "note": "staged only; implementation job did not execute this invocation",
    }


def _model_summary(
    launched: Mapping[str, Any],
    *,
    live: bool,
    used_kind: str,
    requested_model: str,
    catalog_injected: bool,
) -> Dict[str, Any]:
    model = ((launched.get("cursor_acp") or {}).get("model") or {})
    advertised = []
    if not live:
        advertised = list(synthetic_catalog()["advertised_model_ids"])
    return {
        "requested_model": requested_model,
        "advertised_model_ids": advertised,
        "selected_model": model.get("observed_model"),
        "current_model": model.get("observed_model"),
        "source": model.get("source"),
        "live_selector": LIVE_SELECTOR,
        "live_current_model": LIVE_CURRENT_MODEL,
        "official_route_identity": OFFICIAL_ROUTE_IDENTITY,
        "route_resolver": OFFICIAL_RESOLVER_NAME if live else "test_only_cursor_synthetic_route_binding",
        "catalog_injected": catalog_injected,
        "used_kind": used_kind,
        "live_claimed": False,
        "ordinary_launch": "unavailable",
        "available": False,
        "synthetic_catalog_used_as_live": False,
    }


def consume(
    *,
    live: bool = False,
    parent_release: Optional[str] = None,
    state_root: Optional[Path] = None,
    fixture_dir: Optional[Path] = None,
    session: Optional[str] = None,
    continue_turn: bool = True,
    inspect_after: Optional[bool] = None,
    route_resolver: Optional[Callable[[], Any]] = None,
    structured_launch: Optional[Callable[..., Any]] = None,
    inject_post_launch_failure: Optional[str] = None,
    create_workspace: bool = True,
    retain_owned_runtime: Optional[Dict[str, Any]] = None,
    inject_backend_incarnations: Optional[list[Mapping[str, Any]]] = None,
    inject_os_children: Optional[list[Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    reject_live_without_release(live, parent_release)
    (
        default_launch,
        official_resolver,
        synthetic_binding,
        bind_run_transport,
        reject_consumer_bodies,
    ) = _bind_scripts()
    from puppet_lib.cursor_acp import CursorAcpController, require_runtime_task_text

    require_runtime_task_text(FIRST_TASK_TEXT)
    launch = structured_launch or default_launch
    if live:
        session_id = require_explicit_live_session(session)
        owned_paths = live_owned_paths(
            session=session_id,
            state_root=state_root,
            fixture_dir=fixture_dir,
        )
        reject_existing_live_session_paths(owned_paths)
        owned_state = owned_paths["state"]
        workspace_dir = owned_paths["workspace"]
        fence_dir = owned_paths["fence_dir"]
        owned_state.mkdir(parents=True, exist_ok=False)
        if create_workspace:
            workspace = create_fixture_workspace(workspace_dir)
        else:
            raise RuntimeError(LIVE_PATH_EXISTS)
    else:
        session_id = session or "cursor-proof-v3-offline"
        owned_state = Path(state_root) if state_root is not None else V3_ROOT / "state" / session_id
        owned_state.mkdir(parents=True, exist_ok=True)
        workspace_dir = (
            Path(fixture_dir)
            if fixture_dir is not None
            else V3_ROOT / "workspaces" / session_id
        )
        fence_dir = (
            Path(state_root) / "fences" / session_id
            if state_root is not None
            else V3_ROOT / "fences" / session_id
        )
        if create_workspace:
            if workspace_dir.exists():
                shutil.rmtree(workspace_dir)
            workspace = create_fixture_workspace(workspace_dir)
        else:
            workspace = fixture_identity(workspace_dir)
            require_attached_branch(workspace)
    baseline = capture_baseline(workspace_dir)
    protected = baseline["protected_test_sha256"]
    baseline_impl = baseline["implementation_sha256"]

    requested_model = LIVE_SELECTOR if live else SYNTHETIC_REQUESTED
    catalog = None if live else synthetic_catalog()
    resolver = route_resolver
    if resolver is None:
        resolver = official_resolver if live else synthetic_binding
    intended_kind = "official_route" if live and resolver is official_resolver else "synthetic_peer"
    used_kind = intended_kind
    launch_parameters = {
        "entrypoint": "_cursor_acp_structured_launch",
        "requested_model": requested_model,
        "task_text_bound": True,
        "route_resolver": (
            OFFICIAL_RESOLVER_NAME
            if resolver is official_resolver
            else getattr(resolver, "__name__", "substitute")
        ),
        "intended_kind": intended_kind,
        "catalog_injected": catalog is not None,
        "contract_repo": str(workspace_dir.resolve()),
        "expected_workspace_path": str(workspace_dir.resolve()),
        "first_turn_source": FIRST_TURN_SOURCE,
        "owner_next_turn_is_first_turn": False,
    }

    owner = None
    continuation = None
    launched = None
    second = None
    second_ids = None
    second_events = None
    first_ids = None
    first_events = None
    first_process = None
    process_observation = None
    second_observation = None
    backend_mapping = None
    backend_after_finish = None
    finish_attempted = False
    cleanup = None
    cleanup_error: Optional[BaseException] = None
    fence = None
    primary: Optional[BaseException] = None
    runner = None
    isolated_root = None

    def attempt_owner_finish() -> None:
        nonlocal finish_attempted, cleanup, cleanup_error, fence, backend_after_finish
        if finish_attempted or owner is None or continuation is None:
            return
        finish_attempted = True
        try:
            closed = owner.finish(continuation, discard_persistent_state=True)
            reject_consumer_bodies(closed, label="owner finish")
            cleanup = closed
            child_exit = dict(closed.get("child_exit") or {})
            incarnations = merge_backend_incarnations(
                process_observation,
                second_observation,
            )
            backend_after_finish = evaluate_backend_after_finish(
                incarnations,
                live=live,
                cleanup=closed,
            )
            uncertain = evaluate_child_exit(child_exit)
            backend_uncertain = bool(backend_after_finish.get("cleanup_uncertain"))
            if uncertain is not None or backend_uncertain:
                reason = (
                    uncertain["reason"]
                    if uncertain is not None
                    else backend_after_finish["reason"]
                )
                fence = write_cleanup_fence(
                    fence_dir=fence_dir,
                    session=session_id,
                    reason=reason,
                    helper_pid=child_exit.get("pid"),
                    fixture_dir=workspace_dir,
                    state_root=owned_state,
                    extra={
                        "child_exit_exited": child_exit.get("exited"),
                        "backend_after_finish": backend_after_finish,
                    },
                )
                cleanup = dict(closed)
                cleanup["fence"] = fence
        except Exception as cleanup_exc:
            cleanup_error = cleanup_exc
            if runner is not None:
                runner_cleanup = getattr(runner, "cleanup_receipt", None)
                if isinstance(runner_cleanup, Mapping):
                    cleanup = dict(runner_cleanup)
                else:
                    cleanup = {
                        field: getattr(runner, field)
                        for field in (
                            "backend_discard",
                            "worker_termination",
                            "cleanup_uncertain",
                            "replacement_blocked",
                            "worker",
                            "process_lifecycle",
                            "selected_model",
                            "current_model",
                        )
                        if hasattr(runner, field)
                    }
            helper_pid = None
            if runner is not None:
                try:
                    helper_pid = runner.runtime.child_process_identity().get("pid")
                except Exception:
                    helper_pid = None
            fence = write_cleanup_fence(
                fence_dir=fence_dir,
                session=session_id,
                reason="owner.finish raised during driver-owned cleanup",
                helper_pid=helper_pid,
                fixture_dir=workspace_dir,
                state_root=owned_state,
                extra={"cleanup_error_type": type(cleanup_exc).__name__},
            )
            backend_after_finish = evaluate_backend_after_finish(
                merge_backend_incarnations(process_observation, second_observation),
                live=live,
                cleanup=cleanup,
            )
            if primary is None:
                return
            return

    try:
        launched = launch(
            session=session_id,
            contract=make_contract(repo=workspace_dir, requested_model=requested_model),
            transport=bind_run_transport("cursor-acp"),
            state_root=owned_state,
            requested_model=requested_model,
            catalog=catalog,
            prompt=FIRST_TASK_TEXT,
            route_resolver=resolver,
        )
        if FIRST_TASK_TEXT in str(launched) or SECOND_TASK_TEXT in str(launched):
            raise RuntimeError("consumer result retained task text")
        owner = launched["owner"]
        continuation = launched["continuation"]
        reject_consumer_bodies(continuation, label="continuation")
        _distinct_identities(continuation)
        resolved = owner.resolve(continuation)
        runner = resolved["runner"]
        isolated_root = getattr(runner, "isolated_root", None)
        first_process = dict(runner.runtime.child_process_identity())
        used_kind = first_process.get("kind") or used_kind
        # structured_launch already completed the first turn via require_observation.
        process_observation = observe_helper_and_backend(
            first_process,
            sampled_after="structured_launch_first_turn",
            os_children=inject_os_children,
            backend_incarnations=inject_backend_incarnations,
        )
        if retain_owned_runtime is not None:
            retain_owned_runtime["runner"] = runner
            retain_owned_runtime["runtime"] = runner.runtime
            retain_owned_runtime["original_shutdown"] = runner.runtime.shutdown
        first_events = _event_summary(runner)
        first_ids = _public_ids(continuation)
        current_workspace = fixture_identity(workspace_dir)
        if os.path.realpath(current_workspace["path"]) != os.path.realpath(workspace["path"]):
            raise RuntimeError("owned fixture workspace path changed")
        if inject_post_launch_failure == "raise_uncertain":
            runtime = runner.runtime
            runtime.shutdown = lambda: None
            runtime.child_process_identity = lambda: {
                "pid": first_process.get("pid"),
                "returncode": None,
                "exited": False,
                "kind": first_process.get("kind"),
            }
            raise RuntimeError("injected post-launch failure")
        if inject_post_launch_failure == "raise":
            raise RuntimeError("injected post-launch failure")
        backend_mapping = {
            "previous_backend_session_id": first_ids["backend_session_id"],
            "backend_session_id": first_ids["backend_session_id"],
            "previous_runtime_session_name": first_ids["runtime_session_name"],
            "runtime_session_name": first_ids["runtime_session_name"],
            "previous_acpx_record_id": first_ids["acpx_record_id"],
            "acpx_record_id": first_ids["acpx_record_id"],
            "backend_identity_changed": False,
            "assumed_stable_after_reconnect": False,
        }
        if continue_turn:
            second = owner.next_turn(
                continuation,
                text=SECOND_TASK_TEXT,
                request_id="%s-turn-2" % session_id,
                expected_workspace={
                    "path": current_workspace["path"],
                    "branch": current_workspace["branch"],
                    "head": current_workspace["head"],
                    "tree": current_workspace["tree"],
                },
            )
            if FIRST_TASK_TEXT in str(second) or SECOND_TASK_TEXT in str(second):
                raise RuntimeError("continuation retained task text")
            reject_consumer_bodies(second["continuation"], label="continuation")
            second_ids = _public_ids(second["continuation"])
            if second_ids["session"] != first_ids["session"]:
                raise RuntimeError("owned logical session changed")
            if second_ids["request_id"] == first_ids["request_id"]:
                raise RuntimeError("continuation reused the first request id")
            if second_ids["request_id"] == ("%s-turn-1" % session_id):
                raise RuntimeError("owner.next_turn was treated as the first turn")
            backend_mapping.update(
                {
                    "backend_session_id": second_ids["backend_session_id"],
                    "runtime_session_name": second_ids["runtime_session_name"],
                    "acpx_record_id": second_ids["acpx_record_id"],
                    "backend_identity_changed": (
                        second_ids["backend_session_id"] != first_ids["backend_session_id"]
                        or second_ids["acpx_record_id"] != first_ids["acpx_record_id"]
                        or second_ids["runtime_session_name"]
                        != first_ids["runtime_session_name"]
                    ),
                }
            )
            continuation = second["continuation"]
            second_events = _event_summary(owner.resolve(continuation)["runner"])
            second_process = dict(runner.runtime.child_process_identity())
            second_observation = observe_helper_and_backend(
                second_process,
                sampled_after="owner_next_turn_second_turn",
                os_children=inject_os_children,
                backend_incarnations=inject_backend_incarnations,
            )
        if CursorAcpController.available() or owner.available():
            raise RuntimeError("ordinary or default Cursor ACP availability must stay false")
        attempt_owner_finish()
    except BaseException as exc:
        primary = exc
    finally:
        attempt_owner_finish()

    fixture_retained = workspace_dir.is_dir()
    state_retained = owned_state.is_dir()
    if primary is not None:
        if inject_post_launch_failure in {"raise", "raise_uncertain"} and (
            "injected post-launch failure" in str(primary)
        ):
            child_exit = dict((cleanup or {}).get("child_exit") or {})
            if not child_exit and owner is not None:
                child_exit = dict(owner.last_child_exit or {})
            return {
                "schema": "puppet.cursor-live-capable-controller-proof/v3",
                "mode": "injected_post_launch_failure",
                "ok": False,
                "live": False,
                "live_claimed": False,
                "available": False,
                "injected_failure": True,
                "primary_preserved": True,
                "primary_error": _error_label(primary),
                "finish_attempted_once": finish_attempted,
                "cleanup": {
                    "final_discard": None if cleanup is None else cleanup.get("final_discard"),
                    "child_exit": child_exit,
                    "fence": fence,
                    "owner_mediated": True,
                    "cleanup_api": "owner.finish",
                    "backend_after_finish": backend_after_finish,
                },
                "fixture_retained": fixture_retained,
                "state_retained": state_retained,
                "session_replaced": False,
                "workspace": workspace,
                "process": {
                    "first_turn": process_observation,
                    "second_turn": second_observation,
                    "backend_after_finish": backend_after_finish,
                },
                "implementation_job_id": IMPLEMENTATION_JOB_ID,
            }
        raise primary

    child_exit = dict((cleanup or {}).get("child_exit") or {})
    if backend_after_finish is None:
        backend_after_finish = evaluate_backend_after_finish(
            merge_backend_incarnations(process_observation, second_observation),
            live=live,
            cleanup=cleanup,
        )
    uncertain = evaluate_child_exit(child_exit)
    backend_uncertain = bool(backend_after_finish.get("cleanup_uncertain"))
    if fence is None and (uncertain is not None or backend_uncertain):
        reason = (
            uncertain["reason"]
            if uncertain is not None
            else backend_after_finish["reason"]
        )
        fence = write_cleanup_fence(
            fence_dir=fence_dir,
            session=session_id,
            reason=reason,
            helper_pid=child_exit.get("pid"),
            fixture_dir=workspace_dir,
            state_root=owned_state,
            extra={"backend_after_finish": backend_after_finish},
        )
    live_pass_blocked = live and (
        uncertain is not None or backend_uncertain or cleanup_error is not None
    )
    if (not live) and uncertain is not None:
        raise RuntimeError("cleanup uncertain: %s" % uncertain["reason"])

    should_inspect = inspect_after if inspect_after is not None else live
    after = None
    offline_fix = None
    ok = not live_pass_blocked
    if ok and live:
        if should_inspect:
            after = inspect_fixture_after(
                workspace_dir,
                protected_digest=protected,
                require_three=True,
                label="live agent after; independent before/after implementation diff",
                baseline_implementation_sha256=baseline_impl,
            )
    elif ok:
        offline_fix = apply_offline_only_known_answer_fix(workspace_dir)
        after = inspect_fixture_after(
            workspace_dir,
            protected_digest=protected,
            require_three=True,
            label="offline-only known-answer normalization; not useful agent output",
            baseline_implementation_sha256=baseline_impl,
        )

    turn_attribution = {
        "structured_launch_includes_first_turn": True,
        "require_observation_completes_first_turn": True,
        "owner_next_turn_is_first_turn": False,
        "first_turn_source": FIRST_TURN_SOURCE,
        "second_turn_source": SECOND_TURN_SOURCE if second_ids is not None else None,
        "first_request_id": None if first_ids is None else first_ids["request_id"],
        "second_request_id": None if second_ids is None else second_ids["request_id"],
    }
    model_summary = _model_summary(
        launched or {},
        live=live,
        used_kind=used_kind,
        requested_model=requested_model,
        catalog_injected=catalog is not None,
    )
    if runner is not None:
        for key, attr in (("selected_model", "selected_model"), ("current_model", "current_model")):
            value = getattr(runner, attr, None)
            if isinstance(value, str) and value:
                model_summary[key] = value
    receipt = {
        "schema": "puppet.cursor-live-capable-controller-proof/v3",
        "mode": "live_official_route" if live and used_kind == "official_route" else (
            "live_path_substitute" if live else "offline_synthetic"
        ),
        "live": False,
        "live_claimed": False,
        "available": False,
        "ordinary_launch": "unavailable",
        "entrypoint": "_cursor_acp_structured_launch",
        "continuation_api": "owner.next_turn",
        "cleanup_api": "owner.finish",
        "ok": ok,
        "live_cursor_acp_claimed": False if launched is None else launched.get("live_cursor_acp_claimed"),
        "launch_parameters": launch_parameters,
        "turn_attribution": turn_attribution,
        "model": model_summary,
        "host": {
            "session": None if first_ids is None else first_ids["session"],
            "conversation_id": None if first_ids is None else first_ids["host_conversation_id"],
            "first_request_id": None if first_ids is None else first_ids["request_id"],
            "second_request_id": None if second_ids is None else second_ids["request_id"],
        },
        "runtime_ids": {
            "first": None
            if first_ids is None
            else {
                "runtime_session_name": first_ids["runtime_session_name"],
                "backend_session_id": first_ids["backend_session_id"],
                "acpx_record_id": first_ids["acpx_record_id"],
            },
            "second": None
            if second_ids is None
            else {
                "runtime_session_name": second_ids["runtime_session_name"],
                "backend_session_id": second_ids["backend_session_id"],
                "acpx_record_id": second_ids["acpx_record_id"],
            },
            "backend_mapping": backend_mapping,
        },
        "events": {"first": first_events, "second": second_events},
        "process": {
            "first_turn": process_observation,
            "second_turn": second_observation,
            "backend_after_finish": backend_after_finish,
            "helper_exit_sufficient": False,
        },
        "cleanup": {
            "final_discard": None if cleanup is None else cleanup.get("final_discard"),
            "local_release": None if cleanup is None else cleanup.get("local_release"),
            "persistent_state": None if cleanup is None else cleanup.get("persistent_state"),
            "backend_discard": None if cleanup is None else cleanup.get("backend_discard"),
            "worker_termination": None if cleanup is None else cleanup.get("worker_termination"),
            "cleanup_uncertain": None if cleanup is None else cleanup.get("cleanup_uncertain"),
            "replacement_blocked": None if cleanup is None else cleanup.get("replacement_blocked"),
            "worker": None if cleanup is None else cleanup.get("worker"),
            "process_lifecycle": None if cleanup is None else cleanup.get("process_lifecycle"),
            "selected_model": None if cleanup is None else cleanup.get("selected_model"),
            "current_model": None if cleanup is None else cleanup.get("current_model"),
            "child_exit": child_exit,
            "fence": fence,
            "owner_mediated": True,
            "finish_attempted_once": finish_attempted,
            "backend_after_finish": backend_after_finish,
            "finish_error": None if cleanup_error is None else _error_label(cleanup_error),
            "source_contract": source_cleanup_contract(cleanup),
        },
        "workspace": fixture_identity(workspace_dir),
        "source": source_identity(),
        "baseline": baseline,
        "after": after,
        "offline_known_answer": offline_fix,
        "isolated_root": None if isolated_root is None else str(isolated_root),
        "implementation_job_id": IMPLEMENTATION_JOB_ID,
        "fixture_retained": fixture_retained,
        "state_retained": state_retained,
        "session_replaced": False,
    }
    reject_consumer_bodies(receipt, label="v3 receipt")
    if FIRST_TASK_TEXT in str(receipt) or SECOND_TASK_TEXT in str(receipt):
        raise RuntimeError("receipt retained task text")
    return receipt


def reject_placeholder() -> Dict[str, Any]:
    from puppet_lib.cursor_acp import require_runtime_task_text
    from puppet_lib.errors import ValidationError

    try:
        require_runtime_task_text(PLACEHOLDER_TASK_TEXT)
    except ValidationError as exc:
        return {"ok": True, "rejected": "placeholder_task_text", **_error_label(exc)}
    raise RuntimeError("placeholder task text was accepted")


def reject_mismatched_model(*, fixture_dir: Optional[Path] = None) -> Dict[str, Any]:
    (
        structured_launch,
        _official,
        synthetic_binding,
        bind_run_transport,
        _reject,
    ) = _bind_scripts()
    from puppet_lib.errors import IdentityError, ValidationError

    state_root = Path(tempfile.mkdtemp(prefix="cursor-proof-v3-reject-model-"))
    workspace = Path(fixture_dir) if fixture_dir is not None else Path(
        tempfile.mkdtemp(prefix="cursor-proof-v3-model-ws-")
    )
    if fixture_dir is None:
        create_fixture_workspace(workspace)
    try:
        structured_launch(
            session="cursor-proof-v3-reject-model",
            contract=make_contract(repo=workspace, requested_model=LIVE_SELECTOR),
            transport=bind_run_transport("cursor-acp"),
            state_root=state_root,
            requested_model=LIVE_SELECTOR,
            catalog=synthetic_catalog(),
            prompt=FIRST_TASK_TEXT,
            route_resolver=synthetic_binding,
        )
    except (IdentityError, ValidationError) as exc:
        return {"ok": True, "rejected": "mismatched_model", **_error_label(exc)}
    raise RuntimeError("mismatched live selector was accepted by synthetic catalog")


def reject_mismatched_workspace_and_owner(
    *, fixture_dir: Optional[Path] = None
) -> Dict[str, Any]:
    (
        structured_launch,
        _official,
        synthetic_binding,
        bind_run_transport,
        reject_consumer_bodies,
    ) = _bind_scripts()
    from puppet_lib.acp_consumer import AcpConsumerOwner
    from puppet_lib.errors import IdentityError, ValidationError

    state_root = Path(tempfile.mkdtemp(prefix="cursor-proof-v3-reject-ids-"))
    workspace = Path(fixture_dir) if fixture_dir is not None else Path(
        tempfile.mkdtemp(prefix="cursor-proof-v3-ids-ws-")
    )
    if fixture_dir is None:
        create_fixture_workspace(workspace)
    launched = structured_launch(
        session="cursor-proof-v3-reject-ids",
        contract=make_contract(repo=workspace, requested_model=SYNTHETIC_REQUESTED),
        transport=bind_run_transport("cursor-acp"),
        state_root=state_root,
        requested_model=SYNTHETIC_REQUESTED,
        catalog=synthetic_catalog(),
        prompt=FIRST_TASK_TEXT,
        route_resolver=synthetic_binding,
    )
    owner = launched["owner"]
    continuation = launched["continuation"]
    results = []
    try:
        AcpConsumerOwner().next_turn(
            continuation,
            text=SECOND_TASK_TEXT,
            request_id="cursor-proof-v3-reject-ids-turn-3",
        )
        raise RuntimeError("mismatched owner was accepted")
    except ValidationError as exc:
        results.append({"ok": True, "rejected": "mismatched_owner", **_error_label(exc)})
    foreign_session = dict(continuation)
    foreign_session["session"] = "foreign-session"
    try:
        owner.next_turn(
            foreign_session,
            text=SECOND_TASK_TEXT,
            request_id="cursor-proof-v3-reject-ids-turn-4",
        )
        raise RuntimeError("mismatched session was accepted")
    except ValidationError as exc:
        results.append({"ok": True, "rejected": "mismatched_session", **_error_label(exc)})
    foreign = dict(fixture_identity(workspace))
    foreign["path"] = str(state_root / "foreign")
    Path(foreign["path"]).mkdir(parents=True, exist_ok=True)
    try:
        owner.next_turn(
            continuation,
            text=SECOND_TASK_TEXT,
            request_id="cursor-proof-v3-reject-ids-turn-2",
            expected_workspace=foreign,
        )
        raise RuntimeError("mismatched workspace was accepted")
    except IdentityError as exc:
        results.append({"ok": True, "rejected": "mismatched_workspace", **_error_label(exc)})
    cleanup = {
        "final_discard": None,
        "child_exited": (owner.last_child_exit or {}).get("exited"),
        "owner_release_on_failed_next_turn": True,
    }
    try:
        closed = owner.finish(continuation, discard_persistent_state=True)
        reject_consumer_bodies(closed, label="owner finish")
        cleanup = {
            "final_discard": closed.get("final_discard"),
            "child_exited": (closed.get("child_exit") or {}).get("exited"),
            "owner_release_on_failed_next_turn": False,
        }
    except ValidationError:
        if cleanup["child_exited"] is not True:
            raise
    return {
        "ok": all(item["ok"] for item in results),
        "rejections": results,
        "cleanup": cleanup,
    }


def reject_live_flag_without_release() -> Dict[str, Any]:
    try:
        reject_live_without_release(True, None)
    except RuntimeError as exc:
        if LIVE_RELEASE_MISSING not in str(exc):
            raise
        return {"ok": True, "rejected": "live_release_missing", **_error_label(exc)}
    raise RuntimeError("live flag without parent release was accepted")


def scoped_product_diff() -> Dict[str, Any]:
    names = _source_git(["diff", "--name-only", "HEAD"]).splitlines()
    product_prefixes = (
        "skills/",
        "bridge/",
        "tests/",
        "package.json",
        "package-lock.json",
    )
    product = [name for name in names if name.startswith(product_prefixes)]
    return {
        "names": names,
        "product_source_changed": bool(product),
        "product_paths": product,
    }


def run_offline(*, continue_turn: bool = True) -> Dict[str, Any]:
    reject_live_without_release(False, None)
    runtime = verify_existing_runtime()
    consume_receipt = consume(live=False, continue_turn=continue_turn)
    rejections = {
        "placeholder": reject_placeholder(),
        "live_release": reject_live_flag_without_release(),
        "mismatched_model": reject_mismatched_model(),
        "mismatched_ids": reject_mismatched_workspace_and_owner(),
    }
    diff = scoped_product_diff()
    if diff["product_source_changed"]:
        raise RuntimeError("product source changed")
    source = source_identity()
    if source["head"] != EXPECTED_SOURCE_HEAD or source["tree"] != EXPECTED_SOURCE_TREE:
        raise RuntimeError("implementation checkout is not the required PR61 head/tree")
    packet = {
        "schema": "puppet.cursor-live-capable-controller-proof/v3",
        "implementation_job_id": IMPLEMENTATION_JOB_ID,
        "live": False,
        "live_claimed": False,
        "source": source,
        "runtime": runtime,
        "consume": consume_receipt,
        "rejections": rejections,
        "git_diff": diff,
        "staged_live_invocation": staged_live_invocation(),
        "preserved_prior_evidence": {
            "v1_root": str(V1_ROOT),
            "v2_root": str(V2_ROOT),
            "v1_overwritten": False,
            "v2_overwritten": False,
        },
        "remaining_blocker": (
            "parent independent review of this v3 driver, then one parent-issued "
            "--live --parent-release --session on the staged fresh session after "
            "preflight proves workspace/state/fence are absent; no retry and no "
            "live Cursor provider turn has been executed"
        ),
    }
    from puppet_lib.acp_consumer import reject_consumer_bodies

    reject_consumer_bodies(packet, label="v3 offline packet")
    return packet


def write_receipt(packet: Mapping[str, Any], path: Optional[Path] = None) -> Path:
    target = path or (V3_ROOT / "receipts" / "offline-receipt.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n")
    return target


def write_staged_invocation(path: Optional[Path] = None) -> Path:
    target = path or (V3_ROOT / "staged" / "live-invocation.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = staged_live_invocation()
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return target


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live",
        action="store_true",
        help="select the official-route live path; still requires --parent-release and --session",
    )
    parser.add_argument(
        "--parent-release",
        default=None,
        help="parent-issued non-secret release input required with --live",
    )
    parser.add_argument("--no-continue", action="store_true")
    parser.add_argument("--session", default=None)
    args = parser.parse_args(argv)
    if args.live:
        require_parent_release(args.parent_release)
        require_explicit_live_session(args.session)
        packet = consume(
            live=True,
            parent_release=args.parent_release,
            session=args.session,
            continue_turn=not args.no_continue,
        )
        receipt = write_receipt(packet, V3_ROOT / "receipts" / "live-receipt.json")
        print(
            json.dumps(
                {
                    "ok": packet.get("ok"),
                    "live": False,
                    "live_claimed": False,
                    "receipt": str(receipt),
                    "receipt_sha256": sha256_file(receipt),
                    "implementation_job_id": IMPLEMENTATION_JOB_ID,
                    "cleanup": packet.get("cleanup"),
                    "staged_only_note": "caller executed the live path",
                },
                indent=2,
            )
        )
        return 0 if packet.get("ok") else 1
    packet = run_offline(continue_turn=not args.no_continue)
    receipt = write_receipt(packet)
    staged = write_staged_invocation()
    print(
        json.dumps(
            {
                "ok": True,
                "live": False,
                "receipt": str(receipt),
                "receipt_sha256": sha256_file(receipt),
                "implementation_job_id": IMPLEMENTATION_JOB_ID,
                "cleanup": packet["consume"]["cleanup"],
                "staged_live_invocation": str(staged),
                "remaining_blocker": packet["remaining_blocker"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
