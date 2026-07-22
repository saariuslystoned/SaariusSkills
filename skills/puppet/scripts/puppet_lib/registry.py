"""Atomic single-owner session registry and exact identity checks."""

from __future__ import annotations

import ctypes
import errno
import math
import os
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict

from .adapter_manifest import AdapterManifest
from .authority import validate_lease_owner
from .beacons import PREFIXES
from .contracts import Contract, PROCESS_IDENTITY_FIELDS
from .errors import ConflictError, IdentityError, UnsupportedError, ValidationError
from .instructions import validate_instruction_manifest
from .safety import (
    absolute_root,
    atomic_write_json,
    canonical_tmux_socket_path,
    ensure_within,
    exclusive_lock,
    read_json,
    sha256_bytes,
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
    "instructions",
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
    "execution_fingerprint",
    "adapter_fingerprint",
    "protocol_fingerprint",
    "qualification_controller",
    "qualification_campaign_id",
    "qualification_goal_fingerprint",
}
INSTRUCTION_FIELDS = {
    "manifest_path",
    "manifest_sha256",
    "instruction_policy_fingerprint",
    "effective_contract_fingerprint",
    "rendered_sha256",
    "instruction_plane",
    "session_profile",
}
PROCESS_FIELDS = PROCESS_IDENTITY_FIELDS
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
SESSION_REGISTRY_SCHEMA_VERSION = 2
LEGACY_SESSION_REGISTRY_SCHEMA_VERSIONS = frozenset({1})


def validate_process_identity_shape(
    value: Any, label: str = "process"
) -> Dict[str, Any]:
    if not isinstance(value, dict) or set(value) != PROCESS_FIELDS:
        raise ValidationError("%s identity fields do not match schema" % label)
    if (
        value.get("identity_version") != 2
        or isinstance(value.get("pid"), bool)
        or not isinstance(value.get("pid"), int)
        or value["pid"] <= 1
        or not isinstance(value.get("start"), str)
        or not value["start"]
        or len(value["start"]) > 200
        or any(character in value["start"] for character in "\x00\n\r")
        or not isinstance(value.get("kernel_birth_id"), str)
        or not value["kernel_birth_id"]
        or len(value["kernel_birth_id"]) > 200
        or any(character in value["kernel_birth_id"] for character in "\x00\n\r")
        or not isinstance(value.get("command"), str)
        or not value["command"]
        or len(value["command"]) > 1000
        or "\x00" in value["command"]
        or not isinstance(value.get("executable_path"), str)
        or not value["executable_path"]
        or len(value["executable_path"]) > 4096
        or "\x00" in value["executable_path"]
        or not Path(value["executable_path"]).is_absolute()
        or any(
            isinstance(value.get(name), bool)
            or not isinstance(value.get(name), int)
            or value[name] <= 0
            for name in ("device", "inode")
        )
    ):
        raise ValidationError("%s identity is invalid" % label)
    return value


class _DarwinProcBSDInfo(ctypes.Structure):
    _fields_ = [
        ("pbi_flags", ctypes.c_uint32),
        ("pbi_status", ctypes.c_uint32),
        ("pbi_xstatus", ctypes.c_uint32),
        ("pbi_pid", ctypes.c_uint32),
        ("pbi_ppid", ctypes.c_uint32),
        ("pbi_uid", ctypes.c_uint32),
        ("pbi_gid", ctypes.c_uint32),
        ("pbi_ruid", ctypes.c_uint32),
        ("pbi_rgid", ctypes.c_uint32),
        ("pbi_svuid", ctypes.c_uint32),
        ("pbi_svgid", ctypes.c_uint32),
        ("rfu_1", ctypes.c_uint32),
        ("pbi_comm", ctypes.c_char * 16),
        ("pbi_name", ctypes.c_char * 32),
        ("pbi_nfiles", ctypes.c_uint32),
        ("pbi_pgid", ctypes.c_uint32),
        ("pbi_pjobc", ctypes.c_uint32),
        ("e_tdev", ctypes.c_uint32),
        ("e_tpgid", ctypes.c_uint32),
        ("pbi_nice", ctypes.c_int32),
        ("pbi_start_tvsec", ctypes.c_uint64),
        ("pbi_start_tvusec", ctypes.c_uint64),
    ]


class _DarwinProcRegionInfo(ctypes.Structure):
    _fields_ = [
        ("pri_protection", ctypes.c_uint32),
        ("pri_max_protection", ctypes.c_uint32),
        ("pri_inheritance", ctypes.c_uint32),
        ("pri_flags", ctypes.c_uint32),
        ("pri_offset", ctypes.c_uint64),
        ("pri_behavior", ctypes.c_uint32),
        ("pri_user_wired_count", ctypes.c_uint32),
        ("pri_user_tag", ctypes.c_uint32),
        ("pri_pages_resident", ctypes.c_uint32),
        ("pri_pages_shared_now_private", ctypes.c_uint32),
        ("pri_pages_swapped_out", ctypes.c_uint32),
        ("pri_pages_dirtied", ctypes.c_uint32),
        ("pri_ref_count", ctypes.c_uint32),
        ("pri_shadow_depth", ctypes.c_uint32),
        ("pri_share_mode", ctypes.c_uint32),
        ("pri_private_pages_resident", ctypes.c_uint32),
        ("pri_shared_pages_resident", ctypes.c_uint32),
        ("pri_obj_id", ctypes.c_uint32),
        ("pri_depth", ctypes.c_uint32),
        ("pri_address", ctypes.c_uint64),
        ("pri_size", ctypes.c_uint64),
    ]


class _DarwinVinfoStat(ctypes.Structure):
    _fields_ = [
        ("vst_dev", ctypes.c_uint32),
        ("vst_mode", ctypes.c_uint16),
        ("vst_nlink", ctypes.c_uint16),
        ("vst_ino", ctypes.c_uint64),
        ("vst_uid", ctypes.c_uint32),
        ("vst_gid", ctypes.c_uint32),
        ("vst_atime", ctypes.c_int64),
        ("vst_atimensec", ctypes.c_int64),
        ("vst_mtime", ctypes.c_int64),
        ("vst_mtimensec", ctypes.c_int64),
        ("vst_ctime", ctypes.c_int64),
        ("vst_ctimensec", ctypes.c_int64),
        ("vst_birthtime", ctypes.c_int64),
        ("vst_birthtimensec", ctypes.c_int64),
        ("vst_size", ctypes.c_int64),
        ("vst_blocks", ctypes.c_int64),
        ("vst_blksize", ctypes.c_int32),
        ("vst_flags", ctypes.c_uint32),
        ("vst_gen", ctypes.c_uint32),
        ("vst_rdev", ctypes.c_uint32),
        ("vst_qspare", ctypes.c_int64 * 2),
    ]


class _DarwinFsid(ctypes.Structure):
    _fields_ = [("val", ctypes.c_int32 * 2)]


class _DarwinVnodeInfo(ctypes.Structure):
    _fields_ = [
        ("vi_stat", _DarwinVinfoStat),
        ("vi_type", ctypes.c_int),
        ("vi_pad", ctypes.c_int),
        ("vi_fsid", _DarwinFsid),
    ]


class _DarwinVnodeInfoPath(ctypes.Structure):
    _fields_ = [
        ("vip_vi", _DarwinVnodeInfo),
        ("vip_path", ctypes.c_char * 1024),
    ]


class _DarwinProcRegionWithPathInfo(ctypes.Structure):
    _fields_ = [
        ("prp_prinfo", _DarwinProcRegionInfo),
        ("prp_vip", _DarwinVnodeInfoPath),
    ]


_DARWIN_PROC_PIDREGIONPATHINFO = 8
_DARWIN_VM_PROT_EXECUTE = 4
_DARWIN_MAX_REGIONS = 4096
_DARWIN_UINT64_MAX = (1 << 64) - 1
_DARWIN_PROC_PIDTBSDINFO = 3
_DARWIN_PROC_UID_ONLY = 4
_DARWIN_PID_LIST_RETRIES = 3
_DARWIN_PID_LIST_SLACK = 64
_DARWIN_MAX_PROCESS_IDS = 32768


class ExecTransitionSamplingError(IdentityError):
    """A sample crossed a same-PID exec while kernel birth stayed stable."""

    def __init__(
        self,
        message: str,
        *,
        pid: int,
        kernel_birth_id: str,
        executable_before: Dict[str, Any],
        executable_after: Dict[str, Any],
    ):
        super().__init__(message)
        self.pid = pid
        self.kernel_birth_id = kernel_birth_id
        self.executable_before = dict(executable_before)
        self.executable_after = dict(executable_after)


class ProcessExecutableUnavailable(IdentityError):
    """A census entry cannot expose a bindable executable identity."""


class ProcessVanished(IdentityError):
    """The kernel proved that a snapshotted PID no longer exists."""


def _darwin_process_bsd_record(pid: int, libproc: Any = None) -> Dict[str, Any]:
    """Return exact-size BSD identity for one PID through libproc."""

    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 1:
        raise ValidationError("invalid process id")
    try:
        if libproc is None:
            libproc = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
        libproc.proc_pidinfo.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_uint64,
            ctypes.c_void_p,
            ctypes.c_int,
        ]
        libproc.proc_pidinfo.restype = ctypes.c_int
        info = _DarwinProcBSDInfo()
        size = ctypes.sizeof(info)
        ctypes.set_errno(0)
        length = libproc.proc_pidinfo(
            pid,
            _DARWIN_PROC_PIDTBSDINFO,
            0,
            ctypes.byref(info),
            size,
        )
    except (OSError, AttributeError) as exc:
        raise IdentityError("Darwin BSD process identity is unavailable") from exc
    call_errno = ctypes.get_errno()
    if length == 0 and call_errno == errno.ESRCH:
        raise ProcessVanished("snapshotted PID vanished before BSD identity sampling")
    if (
        length != size
        or call_errno != 0
        or info.pbi_pid != pid
        or not 1 <= info.pbi_ppid <= 2**31 - 1
        or info.pbi_uid > 2**32 - 1
        or info.pbi_start_tvsec <= 0
        or info.pbi_start_tvusec >= 1_000_000
    ):
        raise IdentityError("Darwin BSD process identity is unavailable")

    def decoded_name(raw: bytes) -> str:
        try:
            value = raw.split(b"\x00", 1)[0].decode("utf-8")
        except UnicodeDecodeError as exc:
            raise IdentityError("Darwin BSD process command is invalid") from exc
        if len(value) > 1000 or any(character in value for character in "\x00\n\r"):
            raise IdentityError("Darwin BSD process command is invalid")
        return value

    name = decoded_name(bytes(info.pbi_name))
    comm = decoded_name(bytes(info.pbi_comm))
    command = name or comm
    if not command:
        raise IdentityError("Darwin BSD process command is invalid")
    birth = "darwin:%d:%06d" % (
        info.pbi_start_tvsec,
        info.pbi_start_tvusec,
    )
    return {
        "pid": pid,
        "parent_pid": int(info.pbi_ppid),
        "uid": int(info.pbi_uid),
        "kernel_birth_id": birth,
        "start": birth,
        "command": command,
        "name": name,
        "comm": comm,
    }


def _darwin_uid_process_ids(
    libproc: Any = None,
    *,
    max_processes: int = _DARWIN_MAX_PROCESS_IDS,
) -> list[int]:
    """Take a bounded current-UID PID snapshot with truncation retries."""

    if (
        isinstance(max_processes, bool)
        or not isinstance(max_processes, int)
        or max_processes <= 0
        or max_processes > _DARWIN_MAX_PROCESS_IDS
    ):
        raise ValidationError("Darwin process inventory cap is invalid")
    try:
        if libproc is None:
            libproc = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
        libproc.proc_listpids.argtypes = [
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.c_int,
        ]
        libproc.proc_listpids.restype = ctypes.c_int
    except (OSError, AttributeError) as exc:
        raise IdentityError("Darwin process inventory is unavailable") from exc
    integer_size = ctypes.sizeof(ctypes.c_int)
    maximum_bytes = max_processes * integer_size
    uid = os.getuid()

    def required_bytes() -> int:
        ctypes.set_errno(0)
        result = libproc.proc_listpids(_DARWIN_PROC_UID_ONLY, uid, None, 0)
        call_errno = ctypes.get_errno()
        if (
            result <= 0
            or call_errno != 0
            or result % integer_size
            or result > maximum_bytes
        ):
            raise IdentityError("Darwin process inventory size is invalid")
        return result

    for _ in range(_DARWIN_PID_LIST_RETRIES):
        initial_required_bytes = required_bytes()
        initial_required = initial_required_bytes // integer_size
        capacity = min(max_processes, initial_required + _DARWIN_PID_LIST_SLACK)
        if capacity <= initial_required:
            raise IdentityError("Darwin process inventory has no bounded slack")
        capacity_bytes = capacity * integer_size
        buffer = (ctypes.c_int * capacity)()
        ctypes.set_errno(0)
        used_bytes = libproc.proc_listpids(
            _DARWIN_PROC_UID_ONLY,
            uid,
            ctypes.byref(buffer),
            capacity_bytes,
        )
        call_errno = ctypes.get_errno()
        if (
            used_bytes <= 0
            or call_errno != 0
            or used_bytes % integer_size
            or used_bytes > capacity_bytes
        ):
            raise IdentityError("Darwin process inventory payload is invalid")
        post_required_bytes = required_bytes()
        if used_bytes == capacity_bytes or post_required_bytes > initial_required_bytes:
            continue
        pids = [int(buffer[index]) for index in range(used_bytes // integer_size)]
        if (
            not pids
            or len(pids) > max_processes
            or any(pid <= 0 for pid in pids)
            or len(pids) != len(set(pids))
        ):
            raise IdentityError("Darwin process inventory contains invalid PIDs")
        if os.getpid() not in pids:
            continue
        return pids
    raise IdentityError("Darwin process inventory remained truncated or unstable")


def darwin_process_inventory(
    *, max_processes: int = _DARWIN_MAX_PROCESS_IDS
) -> list[Dict[str, Any]]:
    """Return current-UID Darwin PID/UID/start/name rows from one libproc lane."""

    try:
        libproc = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
    except OSError as exc:
        raise IdentityError("Darwin process inventory is unavailable") from exc
    pids = _darwin_uid_process_ids(libproc, max_processes=max_processes)
    records = []
    for pid in pids:
        if pid == 1:
            continue
        try:
            record = _darwin_process_bsd_record(pid, libproc)
        except IdentityError as exc:
            rechecked_pids = _darwin_uid_process_ids(
                libproc, max_processes=max_processes
            )
            if pid not in rechecked_pids:
                continue
            try:
                _darwin_process_bsd_record(pid, libproc)
            except IdentityError as rebound_exc:
                final_pids = _darwin_uid_process_ids(
                    libproc, max_processes=max_processes
                )
                if pid not in final_pids:
                    continue
                raise IdentityError(
                    "Darwin process inventory row remained unavailable"
                ) from rebound_exc
            raise IdentityError(
                "Darwin process inventory PID reappeared with ambiguous identity"
            ) from exc
        if record["uid"] != os.getuid():
            raise IdentityError("Darwin UID-scoped process inventory changed identity")
        records.append(record)
    if not any(record["pid"] == os.getpid() for record in records):
        raise IdentityError("Darwin process inventory lost the controller process")
    return records


def _darwin_kernel_process_record(pid: int) -> Dict[str, Any]:
    record = _darwin_process_bsd_record(pid)
    return {
        "pid": record["pid"],
        "parent_pid": record["parent_pid"],
        "kernel_birth_id": record["kernel_birth_id"],
    }


def _linux_boot_id() -> str:
    try:
        with Path("/proc/sys/kernel/random/boot_id").open("rb") as handle:
            raw = handle.read(129)
        if len(raw) > 128:
            raise IdentityError("kernel boot identity exceeds its bound")
        value = raw.decode("ascii").strip()
    except (OSError, UnicodeError) as exc:
        raise IdentityError("kernel boot identity is unavailable") from exc
    if len(value) != 36 or any(
        (
            character != "-"
            if index in {8, 13, 18, 23}
            else character.lower() not in "0123456789abcdef"
        )
        for index, character in enumerate(value)
    ):
        raise IdentityError("kernel boot identity is invalid")
    return value.lower()


def _linux_kernel_process_record(pid: int) -> Dict[str, Any]:
    try:
        with Path("/proc/%d/stat" % pid).open("rb") as handle:
            raw = handle.read(65537)
        if len(raw) > 65536:
            raise IdentityError("kernel process identity exceeds its bound")
        value = raw.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise IdentityError("kernel process identity is unavailable") from exc
    closing = value.rfind(")")
    if closing <= 0 or not value.startswith("%d (" % pid):
        raise IdentityError("kernel process identity is ambiguous")
    fields = value[closing + 1 :].strip().split()
    if len(fields) < 20:
        raise IdentityError("kernel process identity is ambiguous")
    try:
        parent_pid = int(fields[1])
        start_ticks = int(fields[19])
    except ValueError as exc:
        raise IdentityError("kernel process identity is ambiguous") from exc
    if not 1 <= parent_pid <= 2**31 - 1 or start_ticks <= 0:
        raise IdentityError("kernel process identity is invalid")
    return {
        "pid": pid,
        "parent_pid": parent_pid,
        "kernel_birth_id": "linux:%s:%d" % (_linux_boot_id(), start_ticks),
    }


def _kernel_process_record(pid: int) -> Dict[str, Any]:
    if not isinstance(pid, int) or pid <= 1:
        raise ValidationError("invalid process id")
    if sys.platform == "darwin":
        return _darwin_kernel_process_record(pid)
    if sys.platform.startswith("linux"):
        return _linux_kernel_process_record(pid)
    raise IdentityError("kernel process identity is unsupported on this platform")


def _validated_process_executable_path(value: Any) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 4096
        or "\x00" in value
        or not Path(value).is_absolute()
        or value.endswith(" (deleted)")
    ):
        raise ProcessExecutableUnavailable("process executable path is invalid")
    return value


def _darwin_process_executable_path(pid: int, libproc: Any) -> str:
    try:
        libproc.proc_pidpath.argtypes = [
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.c_uint32,
        ]
        libproc.proc_pidpath.restype = ctypes.c_int
        buffer = ctypes.create_string_buffer(4096)
        length = libproc.proc_pidpath(pid, buffer, len(buffer))
    except (OSError, AttributeError) as exc:
        raise ProcessExecutableUnavailable(
            "process executable identity is unavailable"
        ) from exc
    if length <= 0 or length >= len(buffer):
        raise ProcessExecutableUnavailable("process executable identity is unavailable")
    return _validated_process_executable_path(os.fsdecode(buffer.value))


def _process_executable_path(pid: int) -> str:
    """Return only a kernel-reported display path; never stat this path for authority."""

    if sys.platform == "darwin":
        try:
            libproc = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
        except OSError as exc:
            raise ProcessExecutableUnavailable(
                "process executable identity is unavailable"
            ) from exc
        return _darwin_process_executable_path(pid, libproc)
    if sys.platform.startswith("linux"):
        try:
            value = os.readlink("/proc/%d/exe" % pid)
        except OSError as exc:
            raise ProcessExecutableUnavailable(
                "process executable identity is unavailable"
            ) from exc
        return _validated_process_executable_path(value)
    raise ProcessExecutableUnavailable(
        "process executable identity is unsupported on this platform"
    )


def _darwin_process_executable_record(pid: int) -> Dict[str, Any]:
    """Read the mapped executable vnode identity, not a loaded-byte hash.

    The manifest separately re-hashes the current path through an fd-stable
    snapshot. This sampler proves which vnode is mapped by the process; macOS
    does not expose a process-owned executable descriptor or loaded-page hash
    through this interface.
    """

    try:
        libproc = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
        libproc.proc_pidinfo.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_uint64,
            ctypes.c_void_p,
            ctypes.c_int,
        ]
        libproc.proc_pidinfo.restype = ctypes.c_int
    except (OSError, AttributeError) as exc:
        raise ProcessExecutableUnavailable(
            "process executable identity is unavailable"
        ) from exc
    path_before = _darwin_process_executable_path(pid, libproc)
    address = 0
    identities: set[tuple[int, int]] = set()
    completed = False
    for _ in range(_DARWIN_MAX_REGIONS):
        info = _DarwinProcRegionWithPathInfo()
        size = ctypes.sizeof(info)
        ctypes.set_errno(0)
        try:
            length = libproc.proc_pidinfo(
                pid,
                _DARWIN_PROC_PIDREGIONPATHINFO,
                address,
                ctypes.byref(info),
                size,
            )
        except (OSError, AttributeError) as exc:
            raise ProcessExecutableUnavailable(
                "process executable mapped inventory is unavailable"
            ) from exc
        call_errno = ctypes.get_errno()
        if length == 0:
            if call_errno != errno.EINVAL:
                raise ProcessExecutableUnavailable(
                    "process executable mapped inventory ended with an error"
                )
            completed = True
            break
        if length != size or call_errno != 0:
            raise ProcessExecutableUnavailable(
                "process executable mapped identity is unavailable"
            )
        region = info.prp_prinfo
        region_address = int(region.pri_address)
        region_size = int(region.pri_size)
        if (
            region_address < address
            or region_size <= 0
            or region_address > _DARWIN_UINT64_MAX
            or region_size > _DARWIN_UINT64_MAX - region_address
        ):
            raise ProcessExecutableUnavailable(
                "process executable mapped identity is ambiguous"
            )
        next_address = region_address + region_size
        if next_address <= address:
            raise ProcessExecutableUnavailable(
                "process executable mapped identity is ambiguous"
            )
        raw_path = bytes(info.prp_vip.vip_path).split(b"\x00", 1)[0]
        try:
            region_path = os.fsdecode(raw_path)
        except UnicodeError as exc:
            raise ProcessExecutableUnavailable(
                "process executable mapped path is invalid"
            ) from exc
        vnode = info.prp_vip.vip_vi.vi_stat
        if (
            region_path == path_before
            and region.pri_protection & _DARWIN_VM_PROT_EXECUTE
        ):
            if (
                not stat.S_ISREG(vnode.vst_mode)
                or vnode.vst_dev <= 0
                or vnode.vst_ino <= 0
            ):
                raise ProcessExecutableUnavailable(
                    "process executable mapped identity is invalid"
                )
            identities.add((int(vnode.vst_dev), int(vnode.vst_ino)))
        address = next_address
    if not completed:
        raise ProcessExecutableUnavailable(
            "process executable region inventory exceeds its bound"
        )
    path_after = _darwin_process_executable_path(pid, libproc)
    if path_after != path_before or len(identities) != 1:
        raise ProcessExecutableUnavailable(
            "process executable mapped identity is ambiguous"
        )
    device, inode = identities.pop()
    return {
        "executable_path": path_before,
        "device": device,
        "inode": inode,
    }


def _linux_process_executable_record(pid: int) -> Dict[str, Any]:
    """Open Linux's process-owned executable link and fstat that exact object."""

    proc_path = "/proc/%d/exe" % pid
    path_before = _process_executable_path(pid)
    flags = getattr(os, "O_PATH", os.O_RDONLY) | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(proc_path, flags)
    except OSError as exc:
        raise ProcessExecutableUnavailable(
            "process executable identity is unavailable"
        ) from exc
    try:
        before = os.fstat(descriptor)
        path_after = _process_executable_path(pid)
        after = os.fstat(descriptor)
    except OSError as exc:
        raise ProcessExecutableUnavailable(
            "process executable identity is unavailable"
        ) from exc
    finally:
        os.close(descriptor)
    if (
        path_after != path_before
        or not stat.S_ISREG(before.st_mode)
        or not stat.S_ISREG(after.st_mode)
        or (before.st_dev, before.st_ino, before.st_mode)
        != (after.st_dev, after.st_ino, after.st_mode)
        or after.st_dev <= 0
        or after.st_ino <= 0
    ):
        raise ProcessExecutableUnavailable(
            "process executable identity changed during sampling"
        )
    return {
        "executable_path": path_before,
        "device": after.st_dev,
        "inode": after.st_ino,
    }


def _process_display_record(pid: int) -> Dict[str, str]:
    if sys.platform == "darwin":
        record = _darwin_process_bsd_record(pid)
        return {"start": record["start"], "command": record["command"]}
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
    return {"start": " ".join(parts[:5]), "command": " ".join(parts[5:])}


def _process_executable_record(pid: int) -> Dict[str, Any]:
    if sys.platform == "darwin":
        return _darwin_process_executable_record(pid)
    if sys.platform.startswith("linux"):
        return _linux_process_executable_record(pid)
    raise ProcessExecutableUnavailable(
        "process executable identity is unsupported on this platform"
    )


def _sample_process_binding(
    pid: int,
) -> tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    kernel_before = _kernel_process_record(pid)
    display_before = _process_display_record(pid)
    executable_before = _process_executable_record(pid)
    display_after = _process_display_record(pid)
    executable_after = _process_executable_record(pid)
    kernel_after = _kernel_process_record(pid)
    if any(
        kernel_after[name] != kernel_before[name] for name in ("pid", "kernel_birth_id")
    ):
        raise IdentityError("process identity changed during kernel binding")
    if display_after != display_before or executable_after != executable_before:
        raise ExecTransitionSamplingError(
            "process crossed an exec transition during sampling",
            pid=pid,
            kernel_birth_id=kernel_before["kernel_birth_id"],
            executable_before=executable_before,
            executable_after=executable_after,
        )
    process = {
        "identity_version": 2,
        "pid": pid,
        "kernel_birth_id": kernel_before["kernel_birth_id"],
        **display_before,
        **executable_before,
    }
    return process, kernel_before, kernel_after


def process_tree_identity(pid: int) -> Dict[str, Any]:
    """Bind one process and a stable parent edge to kernel birth identities."""

    process, kernel_before, kernel_after = _sample_process_binding(pid)
    if kernel_after["parent_pid"] != kernel_before["parent_pid"]:
        raise IdentityError("process parent changed during kernel binding")
    return {"process": process, "parent_pid": kernel_before["parent_pid"]}


def process_birth_identity(pid: int) -> Dict[str, Any]:
    process, _, _ = _sample_process_binding(pid)
    return process


def process_executable_identity(pid: int) -> Dict[str, Any]:
    """Bind a lightweight executable selector to one stable kernel birth."""

    kernel_before = _kernel_process_record(pid)
    executable_before = _process_executable_record(pid)
    executable_after = _process_executable_record(pid)
    kernel_after = _kernel_process_record(pid)
    if any(
        kernel_after[name] != kernel_before[name] for name in ("pid", "kernel_birth_id")
    ):
        raise IdentityError("process identity changed during executable census")
    if executable_after != executable_before:
        raise ExecTransitionSamplingError(
            "process crossed an exec transition during executable census",
            pid=pid,
            kernel_birth_id=kernel_before["kernel_birth_id"],
            executable_before=executable_before,
            executable_after=executable_after,
        )
    return {
        "pid": pid,
        "kernel_birth_id": kernel_before["kernel_birth_id"],
        **executable_before,
    }


def bind_runtime_process(
    pid: int,
    manifest: AdapterManifest,
    assert_pane_owner,
    timeout: float | None = None,
    *,
    process_sample_fn=None,
    monotonic_fn=time.monotonic,
    sleep_fn=time.sleep,
    sample_interval: float = 0.05,
) -> Dict[str, Any]:
    """Bind one stable final runtime without following a child or replacement PID."""

    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 1:
        raise ValidationError("runtime process id is invalid")
    if not isinstance(manifest, AdapterManifest) or not callable(assert_pane_owner):
        raise ValidationError("runtime binding inputs are invalid")
    if process_sample_fn is None:
        process_sample_fn = process_birth_identity
    if (
        not callable(process_sample_fn)
        or not callable(monotonic_fn)
        or not callable(sleep_fn)
    ):
        raise ValidationError("runtime binding callbacks are invalid")
    selected_timeout = manifest.execution_settle_timeout if timeout is None else timeout
    if (
        isinstance(selected_timeout, bool)
        or not isinstance(selected_timeout, (int, float))
        or not math.isfinite(float(selected_timeout))
        or selected_timeout <= 0
        or selected_timeout > manifest.execution_settle_timeout
        or isinstance(sample_interval, bool)
        or not isinstance(sample_interval, (int, float))
        or not math.isfinite(float(sample_interval))
        or sample_interval < 0
        or sample_interval > 1
    ):
        raise ValidationError("runtime binding timing is invalid")
    manifest.verify_execution_files()
    deadline = monotonic_fn() + float(selected_timeout)
    pinned_birth = None
    stable_final = None

    def require_pane_owner() -> None:
        if assert_pane_owner(pid) is False:
            raise IdentityError("tmux pane no longer owns the runtime process")

    while True:
        if monotonic_fn() > deadline:
            raise IdentityError("runtime exec transition did not settle before timeout")
        require_pane_owner()
        try:
            process = process_sample_fn(pid)
        except ExecTransitionSamplingError as exc:
            if exc.pid != pid or not exc.kernel_birth_id:
                raise IdentityError(
                    "runtime exec transition identity is ambiguous"
                ) from exc
            if pinned_birth is None:
                pinned_birth = exc.kernel_birth_id
            elif pinned_birth != exc.kernel_birth_id:
                raise IdentityError("runtime process birth identity changed") from exc
            if manifest.raw["execution"]["transition"] != "same_pid_exec":
                raise IdentityError(
                    "direct runtime crossed an undeclared exec transition"
                ) from exc
            try:
                before_class = manifest.classify_executable_identity(
                    exc.executable_before
                )
                after_class = manifest.classify_executable_identity(
                    exc.executable_after
                )
            except (IdentityError, ValidationError) as identity_exc:
                raise IdentityError(
                    "runtime exec transition crossed an undeclared executable"
                ) from identity_exc
            if stable_final is not None or (
                before_class == "runtime" and after_class != "runtime"
            ):
                raise IdentityError("final runtime identity was not stable") from exc
            require_pane_owner()
            sleep_fn(min(float(sample_interval), max(0.0, deadline - monotonic_fn())))
            continue
        require_pane_owner()
        validate_process_identity_shape(process, "runtime process")
        if process["pid"] != pid:
            raise IdentityError("runtime binding cannot follow a forked child")
        birth = process["kernel_birth_id"]
        if pinned_birth is None:
            pinned_birth = birth
        elif birth != pinned_birth:
            raise IdentityError("runtime process birth identity changed")
        classification = manifest.classify_process_executable(process)
        if classification == "transient":
            if stable_final is not None:
                raise IdentityError("final runtime reverted to a transient executable")
        elif stable_final is None:
            stable_final = process
        elif process == stable_final:
            manifest.verify_process_executable(process)
            require_pane_owner()
            return process
        else:
            raise IdentityError("final runtime identity was not stable")
        sleep_fn(min(float(sample_interval), max(0.0, deadline - monotonic_fn())))


def process_alive(identity: Dict[str, Any]) -> bool:
    try:
        current = process_birth_identity(identity["pid"])
    except (IdentityError, KeyError):
        return False
    return current == identity


def process_tree_alive(identity: Dict[str, Any]) -> bool:
    try:
        process = identity["process"]
        current = process_tree_identity(process["pid"])
    except (IdentityError, KeyError, TypeError):
        return False
    return current == identity


def send_exact_sigint(identity: Dict[str, Any]) -> None:
    """Send SIGINT to one revalidated process identity, never to a group."""

    validate_process_identity_shape(identity, "exact signal process")
    pid = identity["pid"]
    if not process_alive(identity):
        raise IdentityError("exact signal process identity changed")
    if (
        sys.platform.startswith("linux")
        and hasattr(os, "pidfd_open")
        and hasattr(signal, "pidfd_send_signal")
    ):
        descriptor = os.pidfd_open(pid, 0)
        try:
            if not process_alive(identity):
                raise IdentityError("exact signal process identity changed")
            signal.pidfd_send_signal(descriptor, signal.SIGINT, None, 0)
        finally:
            os.close(descriptor)
        return
    if not process_alive(identity):
        raise IdentityError("exact signal process identity changed")
    os.kill(pid, signal.SIGINT)


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
        if not isinstance(value, dict):
            raise ValidationError("session registry root must be an object")
        schema_version = value.get("schema_version")
        if schema_version in LEGACY_SESSION_REGISTRY_SCHEMA_VERSIONS:
            raise UnsupportedError(
                "legacy session registry lacks authoritative runtime execution identity"
            )
        if schema_version != SESSION_REGISTRY_SCHEMA_VERSION:
            raise ValidationError("unsupported session registry schema")
        if set(value) != REQUIRED_FIELDS:
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
            Path(supervisor.get("executable_path", "")),
            supervisor_root,
            must_exist=True,
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
        validate_sha256(adapter.get("execution_fingerprint"), "execution fingerprint")
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
        instructions = value.get("instructions")
        if (
            not isinstance(instructions, dict)
            or set(instructions) != INSTRUCTION_FIELDS
        ):
            raise ValidationError("missing instruction manifest identity")
        instruction_path = ensure_within(
            Path(instructions.get("manifest_path", "")),
            proof_root,
            must_exist=True,
        )
        if instruction_path.is_symlink() or not instruction_path.is_file():
            raise ValidationError("invalid bound instruction manifest path")
        for name in (
            "manifest_sha256",
            "instruction_policy_fingerprint",
            "effective_contract_fingerprint",
            "rendered_sha256",
        ):
            validate_sha256(instructions.get(name), name.replace("_", " "))
        if instructions.get("instruction_plane") != "initial_message_wrapper":
            raise ValidationError("unsupported bound instruction plane")
        if instructions.get("session_profile") != "regular":
            raise ValidationError("unsupported bound instruction session profile")
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
        validate_process_identity_shape(server, "registered tmux server")
        if process_birth_identity(server.get("pid")) != server:
            raise ValidationError("registered tmux server birth identity changed")
        if (
            Path(server["executable_path"]).resolve(strict=True) != tmux_path
            or server["device"] != tmux_binary["device"]
            or server["inode"] != tmux_binary["inode"]
        ):
            raise ValidationError("registered tmux server executable mismatch")
        process = value.get("process")
        validate_process_identity_shape(process, "registered process")
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
            "instruction_manifest_sha256",
            "created_at",
        }
        if (
            not isinstance(value, dict)
            or set(value) != required
            or value.get("schema_version") != 1
        ):
            raise ValidationError("invalid session reservation")
        session = validate_identifier(value.get("session"), "session")
        validate_sha256(value.get("contract_fingerprint"), "contract fingerprint")
        validate_sha256(
            value.get("instruction_manifest_sha256"),
            "instruction manifest fingerprint",
        )
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
                or reservation.get("instruction_manifest_sha256")
                != value["instructions"]["manifest_sha256"]
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
        if (
            "session" in changes
            or "schema_version" in changes
            or "instructions" in changes
        ):
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
        if (
            "state" in changes
            or "session" in changes
            or "schema_version" in changes
            or "instructions" in changes
        ):
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
        executable = ensure_within(
            Path(supervisor["executable_path"]), root, must_exist=True
        )
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

    def verify_adapter(
        self, record: Dict[str, Any], capability: str
    ) -> AdapterManifest:
        adapter = record["adapter"]
        proof_root = absolute_root(record["proof_root"], "proof root")
        path = ensure_within(
            Path(adapter["manifest_path"]), proof_root, must_exist=True
        )
        manifest = AdapterManifest.from_path(path)
        if manifest.target != record["target"]:
            raise IdentityError("adapter target identity changed")
        if manifest.fingerprint != adapter["manifest_fingerprint"]:
            raise IdentityError("adapter manifest fingerprint changed")
        if not manifest.identity_matches(
            executable=adapter["executable_fingerprint"],
            execution=adapter["execution_fingerprint"],
            adapter=adapter["adapter_fingerprint"],
            protocol=adapter["protocol_fingerprint"],
        ):
            raise IdentityError("adapter identity changed")
        manifest.verify_execution_files()
        contract = Contract.from_path(Path(record["contract_path"]))
        if (
            contract.fingerprint != record["contract_fingerprint"]
            or contract.target != record["target"]
            or contract.controller != record["controller"]
        ):
            raise IdentityError("bound contract identity changed")
        manifest.verify_qualification(
            expected_controller=adapter["qualification_controller"],
            expected_campaign_id=adapter["qualification_campaign_id"],
            expected_goal_fingerprint=adapter["qualification_goal_fingerprint"],
            expected_session_profile=contract.session_profile,
        )
        manifest.require(capability)
        return manifest

    def verify_instructions(self, record: Dict[str, Any]) -> Dict[str, Any]:
        instructions = record["instructions"]
        proof_root = absolute_root(record["proof_root"], "proof root")
        path = ensure_within(
            Path(instructions["manifest_path"]), proof_root, must_exist=True
        )
        if sha256_file(path, max_bytes=131072) != instructions["manifest_sha256"]:
            raise IdentityError("bound instruction manifest fingerprint changed")
        manifest = validate_instruction_manifest(
            read_json(path, max_bytes=131072, reject_sensitive_fields=True),
            target=record["target"],
        )
        expected = {
            "instruction_policy_fingerprint": manifest[
                "instruction_policy_fingerprint"
            ],
            "effective_contract_fingerprint": manifest[
                "effective_contract_fingerprint"
            ],
            "rendered_sha256": manifest["rendered_sha256"],
            "instruction_plane": manifest["instruction_plane"],
            "session_profile": manifest["session_profile"],
        }
        if any(instructions[name] != observed for name, observed in expected.items()):
            raise IdentityError("bound instruction identity changed")
        contract = Contract.from_path(Path(record["contract_path"]))
        if contract.fingerprint != record["contract_fingerprint"]:
            raise IdentityError("bound instruction contract changed")
        contract_identity = manifest["contract_identity"]
        run_identity = manifest["run_identity"]
        workspace_identity = manifest["workspace_identity"]
        protocol = record["protocol"]
        expected_contract_identity = {
            "fingerprint": contract.fingerprint,
            "controller": contract.controller,
            "target": contract.target,
            "task_profile": contract.task_profile,
        }
        expected_run_identity = {
            "session": record["session"],
            "run_id": protocol["run_id"],
            "nonce": protocol["nonce"],
        }
        expected_orchestration_contract = {
            "mutation_owner": contract.mutation_owner,
            "allowed_modes": sorted(contract.allowed_modes),
            "hard_gates": sorted(contract.hard_gates),
        }
        if (
            contract_identity != expected_contract_identity
            or run_identity != expected_run_identity
            or manifest["orchestration_contract"] != expected_orchestration_contract
            or manifest["runtime_binding"] != {"model": "default", "effort": "default"}
            or set(workspace_identity) != {"repo_fingerprint", "branch", "head", "tree"}
            or workspace_identity.get("repo_fingerprint")
            != sha256_bytes(str(contract.repo).encode("utf-8"))
            or workspace_identity.get("branch") != contract.branch
            or record["controller"] != contract.controller
            or record["target"] != contract.target
            or record["branch"] != contract.branch
        ):
            raise IdentityError("bound instruction authority changed")
        validate_sha1(workspace_identity.get("head"), "instruction workspace head")
        validate_sha1(workspace_identity.get("tree"), "instruction workspace tree")
        return manifest

    def verify_process(self, record: Dict[str, Any]) -> None:
        if not process_alive(record["process"]):
            raise IdentityError("registered process birth identity changed")
        proof_root = absolute_root(record["proof_root"], "proof root")
        path = ensure_within(
            Path(record["adapter"]["manifest_path"]), proof_root, must_exist=True
        )
        manifest = AdapterManifest.from_path(path)
        if manifest.execution_fingerprint != record["adapter"]["execution_fingerprint"]:
            raise IdentityError("registered runtime execution identity changed")
        manifest.verify_process_executable(record["process"])
