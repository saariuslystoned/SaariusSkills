from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .core import (
    DEFAULT_BEACON_TIMEOUT_MS,
    REMOTE_REMOVAL_EVIDENCE,
    cleanup_preserved_tab,
    create_qualification_tab,
    doctor,
    maintenance_checkpoint,
    migrate_legacy_lease_file,
    plan,
    preserve_lease,
    qualification_beacon_wait,
    qualification_harness_ready,
    qualification_reconcile_send,
    qualification_run,
    qualification_send,
    qualification_token_probe,
    register_remote_task_file,
    structural_status,
)
from .errors import HerdrPuppetError
from .herdr_client import MAX_PROMPT_BYTES, HerdrClient, load_json
from .journal import (
    append_event,
    atomic_json,
    initialize_journal,
    make_event,
    refresh_state,
    summarize_journal,
)


RESULTS = {
    "ok",
    "blocked",
    "failed",
    "observed",
    "keep",
    "repair",
    "defer",
    "reject",
    "human_gate",
}


def _write_json(payload: dict[str, Any]) -> None:
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


def _client(args: argparse.Namespace) -> HerdrClient:
    return HerdrClient(args.herdr_bin, args.timeout_seconds)


def _common_live(
    parser: argparse.ArgumentParser,
    *,
    default_timeout_seconds: float = 10.0,
) -> None:
    parser.add_argument("--herdr-bin", default="herdr")
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=default_timeout_seconds,
    )


def _read_prompt(*, text_file: str | None, prompt_stdin: bool) -> str:
    if text_file is not None:
        try:
            with Path(text_file).open("rb") as prompt_stream:
                raw = prompt_stream.read(MAX_PROMPT_BYTES + 1)
        except OSError as exc:
            raise HerdrPuppetError(
                "prompt_read_failed",
                "The prompt file could not be read.",
                details={"path": text_file},
            ) from exc
    elif prompt_stdin:
        stream = getattr(sys.stdin, "buffer", sys.stdin)
        raw = stream.read(MAX_PROMPT_BYTES + 1)
        if isinstance(raw, str):
            raw = raw.encode("utf-8")
    else:
        raise HerdrPuppetError(
            "prompt_source_missing",
            "Choose a non-argv prompt source.",
        )
    if len(raw) > MAX_PROMPT_BYTES:
        raise HerdrPuppetError(
            "prompt_too_large",
            "The prompt exceeds the bounded input size.",
            details={"max_prompt_bytes": MAX_PROMPT_BYTES},
        )
    try:
        prompt = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HerdrPuppetError(
            "invalid_prompt_encoding",
            "The prompt must be valid UTF-8.",
        ) from exc
    if prompt.endswith("\r\n"):
        return prompt[:-2]
    if prompt.endswith(("\r", "\n")):
        return prompt[:-1]
    return prompt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Exact-identity Herdr controller and qualification journal."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor_parser = subparsers.add_parser("doctor")
    doctor_parser.add_argument("--session", required=True)
    doctor_parser.add_argument("--facts-json")
    _common_live(doctor_parser)

    plan_parser = subparsers.add_parser("plan")
    plan_parser.add_argument("--session", required=True)
    plan_parser.add_argument("--workspace-id", required=True)
    plan_parser.add_argument("--workspace-label", required=True)
    plan_parser.add_argument("--expected-ssh-target", required=True)
    plan_parser.add_argument("--run-id", required=True)
    plan_parser.add_argument("--harness", default="agy")
    plan_parser.add_argument("--repo", required=True)
    plan_parser.add_argument("--worktree", required=True)
    plan_parser.add_argument("--proof-root", required=True)
    plan_parser.add_argument("--ordinal", type=int, default=1)
    plan_parser.add_argument("--live-mutation-authorized", action="store_true")
    plan_parser.add_argument("--facts-json")
    plan_parser.add_argument("--output")
    _common_live(plan_parser)

    status_parser = subparsers.add_parser("status")
    record = status_parser.add_mutually_exclusive_group(required=True)
    record.add_argument("--plan-json")
    record.add_argument("--lease-json")
    _common_live(status_parser)

    migrate_lease = subparsers.add_parser("lease-migrate-v1")
    migrate_lease.add_argument("--lease-json", required=True)

    journal_init = subparsers.add_parser("journal-init")
    journal_init.add_argument("--plan-json", required=True)
    journal_init.add_argument("--run-root", required=True)

    journal_append = subparsers.add_parser("journal-append")
    journal_append.add_argument("--run-root", required=True)
    journal_append.add_argument("--run-id", required=True)
    journal_append.add_argument("--kind", required=True)
    journal_append.add_argument("--result", choices=sorted(RESULTS), required=True)
    journal_append.add_argument("--seq", type=int)
    journal_append.add_argument("--note")
    journal_append.add_argument("--data-json")

    journal_show = subparsers.add_parser("journal-show")
    journal_show.add_argument("--run-root", required=True)
    journal_show.add_argument("--recent-limit", type=int, default=20)

    journal_refresh = subparsers.add_parser("journal-refresh")
    journal_refresh.add_argument("--run-root", required=True)
    journal_refresh.add_argument("--lease-json")

    create_tab = subparsers.add_parser("qualification-create-tab")
    create_tab.add_argument("--plan-json", required=True)
    create_tab.add_argument("--lease-json", required=True)
    create_tab.add_argument("--allow-live-qualification", action="store_true")
    create_tab.add_argument("--settle-seconds", type=float, default=10.0)
    create_tab.add_argument("--run-root", required=True)
    _common_live(create_tab)

    run_command = subparsers.add_parser(
        "qualification-run",
        allow_abbrev=False,
    )
    run_command.add_argument("--lease-json", required=True)
    run_command.add_argument("--seq", type=int, required=True)
    run_source = run_command.add_mutually_exclusive_group(required=True)
    run_source.add_argument("--text-file")
    run_source.add_argument(
        "--stdin",
        action="store_true",
        dest="prompt_stdin",
    )
    run_command.add_argument("--run-root")
    run_command.add_argument("--allow-live-qualification", action="store_true")
    _common_live(run_command)

    harness_ready = subparsers.add_parser("qualification-harness-ready")
    harness_ready.add_argument("--lease-json", required=True)
    harness_ready.add_argument("--source-repo", required=True)
    harness_ready.add_argument("--source-worktree", required=True)
    harness_ready.add_argument("--operator-id", required=True)
    harness_ready.add_argument(
        "--evidence",
        choices=["operator_observed_ready_input"],
        required=True,
    )
    harness_ready.add_argument("--confirm-ready", action="store_true")
    harness_ready.add_argument("--run-root", required=True)
    harness_ready.add_argument(
        "--allow-live-qualification",
        action="store_true",
    )
    _common_live(harness_ready)

    send = subparsers.add_parser("qualification-send")
    send.add_argument("--lease-json", required=True)
    send.add_argument("--seq", type=int, required=True)
    send_source = send.add_mutually_exclusive_group(required=True)
    send_source.add_argument("--text-file")
    send_source.add_argument("--stdin", action="store_true", dest="prompt_stdin")
    send.add_argument("--run-root")
    send.add_argument("--allow-live-qualification", action="store_true")
    _common_live(send)

    reconcile = subparsers.add_parser("qualification-reconcile-send")
    reconcile.add_argument("--lease-json", required=True)
    reconcile.add_argument("--seq", type=int, required=True)
    reconcile_source = reconcile.add_mutually_exclusive_group(required=True)
    reconcile_source.add_argument("--text-file")
    reconcile_source.add_argument(
        "--stdin",
        action="store_true",
        dest="prompt_stdin",
    )
    reconcile.add_argument("--evidence", required=True)
    reconcile.add_argument("--confirm-applied", action="store_true")
    reconcile.add_argument("--run-root")
    _common_live(reconcile)

    probe = subparsers.add_parser("qualification-token-probe")
    probe.add_argument("--lease-json", required=True)
    probe.add_argument("--nonce", required=True)
    probe.add_argument("--lines", type=int, default=40)
    probe.add_argument("--timeout-ms", type=int, default=30_000)
    probe.add_argument("--run-root")
    probe.add_argument("--allow-live-qualification", action="store_true")
    _common_live(probe, default_timeout_seconds=35.0)

    beacon = subparsers.add_parser("qualification-beacon-wait")
    beacon.add_argument("--lease-json", required=True)
    beacon.add_argument("--nonce", required=True)
    beacon.add_argument("--lines", type=int, default=40)
    beacon.add_argument(
        "--timeout-ms",
        type=int,
        default=DEFAULT_BEACON_TIMEOUT_MS,
    )
    beacon.add_argument("--run-root", required=True)
    beacon.add_argument("--allow-live-qualification", action="store_true")
    _common_live(beacon, default_timeout_seconds=510.0)

    remote_file = subparsers.add_parser("remote-task-file-register")
    remote_file.add_argument("--lease-json", required=True)
    remote_file.add_argument("--remote-path", required=True)
    remote_file.add_argument("--source-repo", required=True)
    remote_file.add_argument("--source-worktree", required=True)
    remote_file.add_argument("--confirm-caller-owned", action="store_true")
    remote_file.add_argument("--run-root", required=True)

    maintenance = subparsers.add_parser("maintenance-checkpoint")
    maintenance.add_argument("--lease-json", required=True)
    maintenance.add_argument("--run-root", required=True)
    maintenance.add_argument("--remote-task-file-removed")
    maintenance.add_argument(
        "--remote-removal-evidence",
        choices=sorted(REMOTE_REMOVAL_EVIDENCE),
    )
    maintenance.add_argument("--confirm-remote-removed", action="store_true")
    _common_live(maintenance)

    cleanup = subparsers.add_parser("cleanup-preserved-tab")
    cleanup.add_argument("--lease-json", required=True)
    cleanup.add_argument("--run-root", required=True)
    cleanup.add_argument("--confirm-tab-id", required=True)
    cleanup.add_argument("--allow-live-cleanup", action="store_true")
    _common_live(cleanup)

    preserve = subparsers.add_parser("lease-preserve")
    preserve.add_argument("--lease-json", required=True)
    preserve.add_argument(
        "--reason",
        choices=[
            "checkpoint_failed",
            "human_gate",
            "milestone_complete",
            "operator_stop",
            "route_superseded",
        ],
        required=True,
    )
    preserve.add_argument("--run-root")

    return parser


def run(args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "doctor":
        facts = load_json(args.facts_json) if args.facts_json else None
        return doctor(_client(args), args.session, facts=facts)
    if args.command == "plan":
        facts = load_json(args.facts_json) if args.facts_json else None
        payload = plan(
            _client(args),
            session=args.session,
            workspace_id=args.workspace_id,
            workspace_label=args.workspace_label,
            expected_ssh_target=args.expected_ssh_target,
            run_id=args.run_id,
            harness=args.harness,
            repo=args.repo,
            worktree=args.worktree,
            proof_root=args.proof_root,
            ordinal=args.ordinal,
            live_mutation_authorized=args.live_mutation_authorized,
            facts=facts,
        )
        if args.output:
            output = Path(args.output)
            if output.exists():
                raise HerdrPuppetError(
                    "plan_output_exists",
                    "Refusing to overwrite an existing plan output.",
                    details={"output": str(output)},
                )
            atomic_json(output, payload)
        return payload
    if args.command == "status":
        return structural_status(
            _client(args),
            plan_payload=load_json(args.plan_json) if args.plan_json else None,
            lease_payload=load_json(args.lease_json) if args.lease_json else None,
        )
    if args.command == "lease-migrate-v1":
        return migrate_legacy_lease_file(
            lease_payload=load_json(args.lease_json),
            lease_path=Path(args.lease_json),
        )
    if args.command == "journal-init":
        return initialize_journal(Path(args.run_root), load_json(args.plan_json))
    if args.command == "journal-append":
        data = load_json(args.data_json) if args.data_json else None
        event = make_event(
            args.run_id,
            args.kind,
            args.result,
            seq=args.seq,
            note=args.note,
            data=data,
        )
        append_event(Path(args.run_root), event)
        return {
            "schema": "herdr-puppet.journal-append.v1",
            "result": "ok",
            "event": event,
        }
    if args.command == "journal-show":
        return summarize_journal(
            Path(args.run_root),
            recent_limit=args.recent_limit,
        )
    if args.command == "journal-refresh":
        return refresh_state(
            Path(args.run_root),
            load_json(args.lease_json) if args.lease_json else None,
        )
    if args.command == "qualification-create-tab":
        return create_qualification_tab(
            _client(args),
            plan_payload=load_json(args.plan_json),
            lease_path=Path(args.lease_json),
            allow_live=args.allow_live_qualification,
            settle_seconds=args.settle_seconds,
            run_root=Path(args.run_root) if args.run_root else None,
        )
    if args.command == "qualification-run":
        command = _read_prompt(
            text_file=args.text_file,
            prompt_stdin=args.prompt_stdin,
        )
        return qualification_run(
            _client(args),
            lease_payload=load_json(args.lease_json),
            lease_path=Path(args.lease_json),
            seq=args.seq,
            command=command,
            text_file=args.text_file,
            run_root=Path(args.run_root) if args.run_root else None,
            allow_live=args.allow_live_qualification,
        )
    if args.command == "qualification-harness-ready":
        return qualification_harness_ready(
            _client(args),
            lease_payload=load_json(args.lease_json),
            lease_path=Path(args.lease_json),
            source_repo=args.source_repo,
            source_worktree=args.source_worktree,
            operator_id=args.operator_id,
            evidence=args.evidence,
            confirm_ready=args.confirm_ready,
            allow_live=args.allow_live_qualification,
            run_root=Path(args.run_root),
        )
    if args.command == "qualification-send":
        text = _read_prompt(
            text_file=args.text_file,
            prompt_stdin=args.prompt_stdin,
        )
        return qualification_send(
            _client(args),
            lease_payload=load_json(args.lease_json),
            lease_path=Path(args.lease_json),
            seq=args.seq,
            text=text,
            text_file=args.text_file,
            run_root=Path(args.run_root) if args.run_root else None,
            allow_live=args.allow_live_qualification,
        )
    if args.command == "qualification-reconcile-send":
        text = _read_prompt(
            text_file=args.text_file,
            prompt_stdin=args.prompt_stdin,
        )
        return qualification_reconcile_send(
            _client(args),
            lease_payload=load_json(args.lease_json),
            lease_path=Path(args.lease_json),
            seq=args.seq,
            text=text,
            evidence=args.evidence,
            confirm_applied=args.confirm_applied,
            run_root=Path(args.run_root) if args.run_root else None,
        )
    if args.command == "qualification-token-probe":
        return qualification_token_probe(
            _client(args),
            lease_payload=load_json(args.lease_json),
            lease_path=Path(args.lease_json),
            nonce=args.nonce,
            lines=args.lines,
            timeout_ms=args.timeout_ms,
            run_root=Path(args.run_root) if args.run_root else None,
            allow_live=args.allow_live_qualification,
        )
    if args.command == "qualification-beacon-wait":
        return qualification_beacon_wait(
            _client(args),
            lease_payload=load_json(args.lease_json),
            lease_path=Path(args.lease_json),
            nonce=args.nonce,
            lines=args.lines,
            timeout_ms=args.timeout_ms,
            run_root=Path(args.run_root) if args.run_root else None,
            allow_live=args.allow_live_qualification,
        )
    if args.command == "remote-task-file-register":
        return register_remote_task_file(
            lease_payload=load_json(args.lease_json),
            lease_path=Path(args.lease_json),
            remote_path=args.remote_path,
            source_repo=args.source_repo,
            source_worktree=args.source_worktree,
            confirm_caller_owned=args.confirm_caller_owned,
            run_root=Path(args.run_root),
        )
    if args.command == "maintenance-checkpoint":
        return maintenance_checkpoint(
            _client(args),
            lease_payload=load_json(args.lease_json),
            lease_path=Path(args.lease_json),
            run_root=Path(args.run_root),
            remote_removed_path=args.remote_task_file_removed,
            remote_removal_evidence=args.remote_removal_evidence,
            confirm_remote_removed=args.confirm_remote_removed,
        )
    if args.command == "cleanup-preserved-tab":
        return cleanup_preserved_tab(
            _client(args),
            lease_payload=load_json(args.lease_json),
            lease_path=Path(args.lease_json),
            run_root=Path(args.run_root),
            confirm_tab_id=args.confirm_tab_id,
            allow_live_cleanup=args.allow_live_cleanup,
        )
    if args.command == "lease-preserve":
        return preserve_lease(
            lease_payload=load_json(args.lease_json),
            lease_path=Path(args.lease_json),
            reason=args.reason,
            run_root=Path(args.run_root) if args.run_root else None,
        )
    raise HerdrPuppetError("unknown_command", "Unknown command.")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        payload = run(args)
    except HerdrPuppetError as exc:
        _write_json(exc.as_json())
        return exc.exit_code
    except OSError as exc:
        error = HerdrPuppetError(
            "filesystem_error",
            "A local controller file operation failed.",
            details={"message": str(exc)},
        )
        _write_json(error.as_json())
        return error.exit_code
    _write_json(payload)
    return (
        0
        if payload.get("result") not in {"blocked", "not_matched", "human_gate"}
        else 3
    )
