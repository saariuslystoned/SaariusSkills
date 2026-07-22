"""Atomic single-owner session registry and exact identity checks."""

from __future__ import annotations

import ctypes
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

from .adapter_manifest import AdapterManifest
from .authority import validate_lease_owner
from .beacons import PREFIXES
from .errors import ConflictError, IdentityError, ValidationError
from .safety import (
    absolute_root,
    atomic_write_json,
    canonical_tmux_socket_path,
    ensure_within,
    exclusive_lock,
    read_json,
    sha256_file,
    validate_bounded_json,
    validate_branch,
    validate_identifier,
    validate_pane_id,
    validate_sha1,
    validate_sha256,
)
from .state import transition, validate_state


REQUIRED_FIELDS = {
    "schema_version",
    "session",
    "controller",
    "target",
    "lease_owner",
    "contract_fingerprint",
    "contract_path",
    "state",
    "repo",
    "branch",
    "mutation_owner",
    "proof_root",
    "tmux",
    "process",
    "supervisor",
    "adapter",
    "protocol",
    "created_at",
    "last_checkpoint",
    "last_beacon",
    "blocker",
}

SUPERVISOR_FIELDS = {
    "root",
    "commit",
    "tree",
    "executable_path",
    "executable_sha256",
}
ADAPTER_FIELDS = {
    "manifest_path",
    "manifest_fingerprint",
    "executable_fingerprint",
    "adapter_fingerprint",
    "protocol_fingerprint",
    "qualification_controller",
    "qualification_campaign_id",
    "qualification_goal_fingerprint",
}
PROCESS_FIELDS = {
    "pid",
    "start",
    "command",
    "executable_path",
    "device",
    "inode",
}
TMUX_BINARY_FIELDS = {
    "path",
    "device",
    "inode",
    "uid",
    "gid",
    "mode",
    "size",
    "sha256",
    "version",
}


def _process_executable_path(pid: int) -> Path:
    if sys.platform == "darwin":
        try:
            libproc = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
            buffer = ctypes.create_string_buffer(4096)
            length = libproc.proc_pidpath(pid, buffer, len(buffer))
        except (OSError, AttributeError) as exc:
            raise IdentityError("process executable identity is unavailable") from exc
        if length <= 0:
            raise IdentityError("process executable identity is unavailable")
        path = Path(os.fsdecode(buffer.value))
    elif sys.platform.startswith("linux"):
        try:
            path = Path(os.readlink("/proc/%d/exe" % pid))
        except OSError as exc:
            raise IdentityError("process executable identity is unavailable") from exc
    else:
        raise IdentityError("process executable identity is unsupported on this platform")
    if path.is_symlink() or not path.is_file():
        raise IdentityError("process executable path is invalid")
    return path.resolve(strict=True)


def process_birth_identity(pid: int) -> Dict[str, Any]:
    if not isinstance(pid, int) or pid <= 1:
        raise ValidationError("invalid process id")
    result = subprocess.run(
        ["ps", "-p", str(pid), "-o", "lstart=,comm="],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
        text=True,
    )
    line = result.stdout.strip()
    if result.returncode != 0 or not line:
        raise IdentityError("registered target process is unavailable")
    parts = line.split()
    if len(parts) < 6:
        raise IdentityError("process birth identity is ambiguous")
    executable = _process_executable_path(pid)
    executable_stat = executable.stat()
    return {
        "pid": pid,
        "start": " ".join(parts[:5]),
        "command": " ".join(parts[5:]),
        "executable_path": str(executable),
        "device": executable_stat.st_dev,
        "inode": executable_stat.st_ino,
    }


def process_alive(identity: Dict[str, Any]) -> bool:
    try:
        current = process_birth_identity(identity["pid"])
    except (IdentityError, KeyError):
        return False
    return current == identity


class SessionRegistry:
    def __init__(self, root: Path):
        requested = Path(root)
        if requested.exists() and requested.is_symlink():
            raise ValidationError("state root must not be a symlink")
        requested.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.root = requested.resolve(strict=True)
        self.sessions = self.root / "sessions"
        if self.sessions.exists() and self.sessions.is_symlink():
            raise ValidationError("sessions root must not be a symlink")
        self.sessions.mkdir(mode=0o700, exist_ok=True)
        self.reservations = self.root / "reservations"
        if self.reservations.exists() and self.reservations.is_symlink():
            raise ValidationError("reservations root must not be a symlink")
        self.reservations.mkdir(mode=0o700, exist_ok=True)

    def _path(self, session: str) -> Path:
        validate_identifier(session, "session")
        return self.sessions / (session + ".json")

    def _lock(self, session: str) -> Path:
        return self.sessions / (".%s.lock" % validate_identifier(session, "session"))

    def operation_lock(self, session: str) -> Path:
        return self.sessions / (
            ".%s.operation.lock" % validate_identifier(session, "session")
        )

    def _reservation_path(self, session: str) -> Path:
        validate_identifier(session, "session")
        return self.reservations / (session + ".json")

    def validate(self, value: Dict[str, Any]) -> Dict[str, Any]:
        if set(value) != REQUIRED_FIELDS or value.get("schema_version") != 1:
            raise ValidationError("session registry fields do not match schema")
        validate_identifier(value.get("session"), "session")
        validate_identifier(value.get("controller"), "controller")
        if value.get("target") not in {"agy", "cursor", "claude", "codex", "grok"}:
            raise ValidationError("unsupported session target")
        if validate_lease_owner(value.get("lease_owner")) != value["lease_owner"]:
            raise IdentityError("session lease owner identity changed")
        validate_sha256(value.get("contract_fingerprint"), "contract fingerprint")
        proof_root = absolute_root(value.get("proof_root"), "proof root")
        contract_path = ensure_within(
            Path(value.get("contract_path", "")), proof_root, must_exist=True
        )
        if contract_path.is_symlink() or not contract_path.is_file():
            raise ValidationError("invalid bound contract path")
        validate_state(value.get("state"))
        absolute_root(value.get("repo"), "repo")
        validate_branch(value.get("branch"))
        if value.get("mutation_owner") not in {"none", "target"}:
            raise ValidationError("invalid mutation owner")
        supervisor = value.get("supervisor")
        if not isinstance(supervisor, dict) or set(supervisor) != SUPERVISOR_FIELDS:
            raise ValidationError("missing supervisor identity")
        supervisor_root = absolute_root(supervisor.get("root"), "supervisor root")
        validate_sha1(supervisor.get("commit"), "supervisor commit")
        validate_sha1(supervisor.get("tree"), "supervisor tree")
        validate_sha256(supervisor.get("executable_sha256"), "supervisor executable")
        supervisor_executable = ensure_within(
            Path(supervisor.get("executable_path", "")), supervisor_root, must_exist=True
        )
        if supervisor_executable.is_symlink() or not supervisor_executable.is_file():
            raise ValidationError("invalid supervisor executable")
        adapter = value.get("adapter")
        if not isinstance(adapter, dict) or set(adapter) != ADAPTER_FIELDS:
            raise ValidationError("missing adapter identity")
        manifest_path = ensure_within(
            Path(adapter.get("manifest_path", "")), proof_root, must_exist=True
        )
        if manifest_path.is_symlink() or not manifest_path.is_file():
            raise ValidationError("invalid bound adapter manifest path")
        validate_sha256(adapter.get("manifest_fingerprint"), "manifest fingerprint")
        validate_sha256(adapter.get("executable_fingerprint"), "executable fingerprint")
        validate_sha256(adapter.get("adapter_fingerprint"), "adapter fingerprint")
        validate_sha256(adapter.get("protocol_fingerprint"), "protocol fingerprint")
        validate_identifier(
            adapter.get("qualification_controller"), "qualification controller"
        )
        validate_identifier(
            adapter.get("qualification_campaign_id"), "qualification campaign id"
        )
        validate_sha256(
            adapter.get("qualification_goal_fingerprint"),
            "qualification goal fingerprint",
        )
        tmux = value.get("tmux")
        if not isinstance(tmux, dict) or set(tmux) != {
            "socket",
            "socket_identity",
            "session",
            "pane",
            "server_identity",
            "tmux_binary_identity",
        }:
            raise ValidationError("invalid tmux identity")
        if tmux["session"] != value["session"]:
            raise ValidationError("tmux session identity mismatch")
        validate_pane_id(tmux["pane"])
        expected_socket = canonical_tmux_socket_path(self.root, value["session"])
        if tmux["socket"] != str(expected_socket):
            raise ValidationError("tmux socket is outside the session authority")
        socket_path = Path(tmux["socket"])
        if socket_path.is_symlink() or not socket_path.exists():
            raise ValidationError("registered tmux socket is unavailable")
        if not stat.S_ISSOCK(socket_path.stat().st_mode):
            raise ValidationError("registered tmux path is not a socket")
        socket_details = socket_path.stat()
        socket_identity = tmux["socket_identity"]
        expected_socket_identity = {
            "device": socket_details.st_dev,
            "inode": socket_details.st_ino,
            "uid": socket_details.st_uid,
            "mode": stat.S_IMODE(socket_details.st_mode),
        }
        if socket_identity != expected_socket_identity:
            raise ValidationError("registered tmux socket identity changed")
        if socket_details.st_uid != os.getuid() or socket_details.st_mode & 0o077:
            raise ValidationError("registered tmux socket is not user-private")
        tmux_binary = tmux["tmux_binary_identity"]
        if not isinstance(tmux_binary, dict) or set(tmux_binary) != TMUX_BINARY_FIELDS:
            raise ValidationError("registered tmux executable identity is invalid")
        tmux_path = Path(tmux_binary.get("path", ""))
        if (
            not tmux_path.is_absolute()
            or tmux_path.is_symlink()
            or not tmux_path.is_file()
            or not isinstance(tmux_binary.get("version"), str)
            or not tmux_binary["version"]
            or len(tmux_binary["version"]) > 200
        ):
            raise ValidationError("registered tmux executable is unavailable")
        validate_sha256(tmux_binary.get("sha256"), "tmux executable")
        tmux_details = tmux_path.stat()
        if tmux_binary != {
            "path": str(tmux_path.resolve(strict=True)),
            "device": tmux_details.st_dev,
            "inode": tmux_details.st_ino,
            "uid": tmux_details.st_uid,
            "gid": tmux_details.st_gid,
            "mode": stat.S_IMODE(tmux_details.st_mode),
            "size": tmux_details.st_size,
            "sha256": sha256_file(tmux_path),
            "version": tmux_binary["version"],
        }:
            raise ValidationError("registered tmux executable identity changed")
        server = tmux["server_identity"]
        if not isinstance(server, dict) or set(server) != PROCESS_FIELDS:
            raise ValidationError("registered tmux server identity is invalid")
        if process_birth_identity(server.get("pid")) != server:
            raise ValidationError("registered tmux server birth identity changed")
        if (
            Path(server["executable_path"]).resolve(strict=True) != tmux_path
            or server["device"] != tmux_binary["device"]
            or server["inode"] != tmux_binary["inode"]
        ):
            raise ValidationError("registered tmux server executable mismatch")
        process = value.get("process")
        if not isinstance(process, dict) or set(process) != PROCESS_FIELDS:
            raise ValidationError("invalid process identity")
        process_executable = Path(process["executable_path"])
        if not process_executable.is_absolute():
            raise ValidationError("process executable path must be absolute")
        for name in ("pid", "device", "inode"):
            if (
                isinstance(process.get(name), bool)
                or not isinstance(process.get(name), int)
                or process[name] <= 0
            ):
                raise ValidationError("invalid process %s identity" % name)
        protocol = value.get("protocol")
        if not isinstance(protocol, dict) or protocol.get("kind") not in {
            "conformance",
            "source",
        }:
            raise ValidationError("invalid protocol state")
        validate_identifier(protocol.get("run_id"), "run id")
        validate_identifier(protocol.get("nonce"), "nonce")
        if protocol["kind"] == "conformance":
            required = {
                "kind",
                "run_id",
                "nonce",
                "phase",
                "fixture_fingerprint",
                "ready_checkpoint_id",
                "ready_artifact_sha256",
                "message_id",
                "followup_checkpoint_id",
            }
            if set(protocol) != required:
                raise ValidationError("invalid conformance protocol fields")
            validate_sha256(protocol["fixture_fingerprint"], "fixture fingerprint")
            if protocol["phase"] not in {
                "awaiting_ready",
                "ready_validated",
                "followup_sent",
                "followup_validated",
                "reviewed",
                "accepted",
            }:
                raise ValidationError("invalid conformance protocol phase")
            for name in (
                "ready_checkpoint_id",
                "ready_artifact_sha256",
                "followup_checkpoint_id",
            ):
                if protocol[name] is not None:
                    validate_sha256(protocol[name], name.replace("_", " "))
            if protocol["message_id"] is not None:
                validate_identifier(protocol["message_id"], "message id")
            identities = (
                protocol["ready_checkpoint_id"],
                protocol["ready_artifact_sha256"],
                protocol["message_id"],
                protocol["followup_checkpoint_id"],
            )
            expected_presence = {
                "awaiting_ready": (False, False, False, False),
                "ready_validated": (True, True, False, False),
                "followup_sent": (True, True, True, False),
                "followup_validated": (True, True, True, True),
                "reviewed": (True, True, True, True),
                "accepted": (True, True, True, True),
            }[protocol["phase"]]
            if tuple(item is not None for item in identities) != expected_presence:
                raise ValidationError("conformance protocol identity is incomplete")
        else:
            required = {
                "kind",
                "run_id",
                "nonce",
                "phase",
                "source_commit",
                "proof_commit",
            }
            if set(protocol) != required:
                raise ValidationError("invalid source protocol fields")
            if protocol["phase"] not in {
                "awaiting_source",
                "source_checkpoint",
                "source_accepted",
                "proof_checkpoint",
                "final_reviewed",
                "accepted",
            }:
                raise ValidationError("invalid source protocol phase")
            for name in ("source_commit", "proof_commit"):
                if protocol[name] is not None:
                    validate_sha1(protocol[name], name.replace("_", " "))
            source_present = protocol["source_commit"] is not None
            proof_present = protocol["proof_commit"] is not None
            expected_presence = {
                "awaiting_source": (False, False),
                "source_checkpoint": (True, False),
                "source_accepted": (True, False),
                "proof_checkpoint": (True, True),
                "final_reviewed": (True, True),
                "accepted": (True, True),
            }[protocol["phase"]]
            if (source_present, proof_present) != expected_presence:
                raise ValidationError("source protocol identity is incomplete")
        beacon = value.get("last_beacon")
        if beacon is not None:
            if not isinstance(beacon, dict) or set(beacon) != {
                "received_at",
                "prefix",
                "kind",
                "authority",
                "data",
            }:
                raise ValidationError("invalid last beacon projection")
            if not isinstance(beacon["received_at"], str) or not beacon["received_at"]:
                raise ValidationError("last beacon timestamp is missing")
            if beacon["authority"] != "target_claim":
                raise ValidationError("last beacon authority is invalid")
            if PREFIXES.get(beacon["prefix"]) != beacon["kind"]:
                raise ValidationError("last beacon prefix or kind is invalid")
            if not isinstance(beacon["data"], dict):
                raise ValidationError("last beacon data is invalid")
            validate_bounded_json(
                beacon["data"],
                max_depth=4,
                max_items=32,
                max_string=512,
                reject_sensitive_fields=True,
            )
        return value

    def exists(self, session: str) -> bool:
        return self._path(session).exists() or self._reservation_path(session).exists()

    def reserve(self, value: Dict[str, Any]) -> Dict[str, Any]:
        required = {
            "schema_version",
            "session",
            "contract_fingerprint",
            "proof_root",
            "expected_socket",
            "created_at",
        }
        if not isinstance(value, dict) or set(value) != required or value.get("schema_version") != 1:
            raise ValidationError("invalid session reservation")
        session = validate_identifier(value.get("session"), "session")
        validate_sha256(value.get("contract_fingerprint"), "contract fingerprint")
        absolute_root(value.get("proof_root"), "proof root")
        expected_socket = canonical_tmux_socket_path(self.root, session)
        if value.get("expected_socket") != str(expected_socket):
            raise ValidationError("reservation socket identity mismatch")
        if not isinstance(value.get("created_at"), str) or not value["created_at"]:
            raise ValidationError("reservation timestamp is missing")
        with exclusive_lock(self._lock(session)):
            if self._path(session).exists() or self._reservation_path(session).exists():
                raise ConflictError("session is already reserved or registered")
            atomic_write_json(self._reservation_path(session), value)
        return value

    def activate(self, value: Dict[str, Any]) -> Dict[str, Any]:
        self.validate(value)
        session = value["session"]
        with exclusive_lock(self._lock(session)):
            reservation_path = self._reservation_path(session)
            if not reservation_path.exists():
                raise ConflictError("session has no launch reservation")
            reservation = read_json(reservation_path, max_bytes=16384)
            if (
                reservation.get("contract_fingerprint") != value["contract_fingerprint"]
                or reservation.get("proof_root") != value["proof_root"]
                or reservation.get("expected_socket") != value["tmux"]["socket"]
            ):
                raise IdentityError("session reservation identity changed")
            if self._path(session).exists():
                raise ConflictError("session is already registered")
            atomic_write_json(self._path(session), value)
            reservation_path.unlink()
        return value

    def release_reservation(self, session: str, contract_fingerprint: str) -> None:
        validate_sha256(contract_fingerprint, "contract fingerprint")
        with exclusive_lock(self._lock(session)):
            path = self._reservation_path(session)
            if not path.exists():
                return
            value = read_json(path, max_bytes=16384)
            if value.get("contract_fingerprint") != contract_fingerprint:
                raise IdentityError("reservation identity changed")
            if self._path(session).exists():
                raise ConflictError("cannot release an activated reservation")
            path.unlink()

    def create(self, value: Dict[str, Any]) -> Dict[str, Any]:
        self.validate(value)
        session = value["session"]
        with exclusive_lock(self._lock(session)):
            destination = self._path(session)
            if destination.exists():
                raise ConflictError("session is already registered")
            atomic_write_json(destination, value)
        return value

    def load(self, session: str) -> Dict[str, Any]:
        path = self._path(session)
        if not path.exists():
            raise ValidationError("unknown session")
        return self.validate(read_json(path, max_bytes=131072))

    def update(self, session: str, changes: Dict[str, Any]) -> Dict[str, Any]:
        if "session" in changes or "schema_version" in changes:
            raise ValidationError("immutable registry identity cannot change")
        with exclusive_lock(self._lock(session)):
            current = self.load(session)
            if "state" in changes:
                transition(current["state"], changes["state"])
            updated = dict(current)
            updated.update(changes)
            self.validate(updated)
            atomic_write_json(self._path(session), updated)
            return updated

    def transition_path(
        self, session: str, states: list, changes: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        if not isinstance(states, list) or not states:
            raise ValidationError("transition path must be a non-empty list")
        changes = dict(changes or {})
        if "state" in changes or "session" in changes or "schema_version" in changes:
            raise ValidationError("transition path contains an immutable change")
        with exclusive_lock(self._lock(session)):
            current = self.load(session)
            next_state = current["state"]
            for requested in states:
                next_state = transition(next_state, requested)
            updated = dict(current)
            updated.update(changes)
            updated["state"] = next_state
            self.validate(updated)
            atomic_write_json(self._path(session), updated)
            return updated

    def verify_supervisor(self, record: Dict[str, Any]) -> None:
        supervisor = record["supervisor"]
        root = absolute_root(supervisor["root"], "supervisor root")
        executable = ensure_within(Path(supervisor["executable_path"]), root, must_exist=True)
        if executable.is_symlink() or not executable.is_file():
            raise IdentityError("supervisor executable path is invalid")
        if sha256_file(executable) != supervisor["executable_sha256"]:
            raise IdentityError("supervisor executable fingerprint changed")

        def git(arguments):
            result = subprocess.run(
                ["git", "-C", str(root)] + arguments,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                raise IdentityError("supervisor release identity is unavailable")
            return result.stdout.strip()

        if git(["rev-parse", "HEAD"]) != supervisor["commit"]:
            raise IdentityError("supervisor commit changed")
        if git(["rev-parse", "HEAD^{tree}"]) != supervisor["tree"]:
            raise IdentityError("supervisor tree changed")
        relative = str(executable.relative_to(root))
        git(["ls-files", "--error-unmatch", "--", relative])
        if git(["status", "--porcelain=v1", "--untracked-files=all"]):
            raise IdentityError("supervisor release is not immutable and clean")

    def verify_adapter(self, record: Dict[str, Any], capability: str) -> AdapterManifest:
        adapter = record["adapter"]
        proof_root = absolute_root(record["proof_root"], "proof root")
        path = ensure_within(Path(adapter["manifest_path"]), proof_root, must_exist=True)
        manifest = AdapterManifest.from_path(path)
        if manifest.target != record["target"]:
            raise IdentityError("adapter target identity changed")
        if manifest.fingerprint != adapter["manifest_fingerprint"]:
            raise IdentityError("adapter manifest fingerprint changed")
        if not manifest.identity_matches(
            executable=adapter["executable_fingerprint"],
            adapter=adapter["adapter_fingerprint"],
            protocol=adapter["protocol_fingerprint"],
        ):
            raise IdentityError("adapter identity changed")
        executable = Path(manifest.raw["executable"]["resolved_path"])
        if executable.is_symlink() or not executable.is_file():
            raise IdentityError("adapter executable is unavailable")
        executable_stat = executable.stat()
        expected_executable = manifest.raw["executable"]
        if any(
            executable_stat_value != expected_executable[name]
            for name, executable_stat_value in (
                ("device", executable_stat.st_dev),
                ("inode", executable_stat.st_ino),
                ("size", executable_stat.st_size),
                ("mtime_ns", executable_stat.st_mtime_ns),
            )
        ):
            raise IdentityError("adapter executable file identity changed")
        if sha256_file(executable) != adapter["executable_fingerprint"]:
            raise IdentityError("adapter executable fingerprint changed")
        manifest.verify_qualification(
            expected_controller=adapter["qualification_controller"],
            expected_campaign_id=adapter["qualification_campaign_id"],
            expected_goal_fingerprint=adapter["qualification_goal_fingerprint"],
        )
        manifest.require(capability)
        return manifest

    def verify_process(self, record: Dict[str, Any]) -> None:
        if not process_alive(record["process"]):
            raise IdentityError("registered process birth identity changed")
