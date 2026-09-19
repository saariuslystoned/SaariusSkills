from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any

from .core import (
    DEFAULT_BEACON_TIMEOUT_MS,
    REMOTE_REMOVAL_EVIDENCE,
    cleanup_preserved_tab,
    create_qualification_tab,
    doctor,
    load_destination_catalog,
    maintenance_checkpoint,
    migrate_legacy_lease_file,
    plan,
    plan_selection_receipt,
    preserve_lease,
    qualification_beacon_wait,
    qualification_claude_lifecycle_observe,
    qualification_claude_receipt_command,
    qualification_harness_census_verify,
    qualification_harness_launch,
    qualification_harness_ready,
    qualification_reconcile_send,
    qualification_run,
    qualification_send,
    qualification_startup_gate,
    qualification_token_probe,
    qualification_view_begin,
    qualification_view_complete,
    register_remote_task_file,
    resume_lease,
    structural_status,
)
from .errors import HerdrPuppetError
from .harness_binding import (
    CANONICAL_HARNESSES,
    build_harness_binding,
    compile_instruction_wrapper,
    write_create_only,
)
from .herdr_client import MAX_PROMPT_BYTES, HerdrClient, load_json
from .journal import (
    append_event,
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


def _load_bounded_receipt(path_value: str) -> dict[str, Any]:
    def reject_duplicate_fields(
        pairs: list[tuple[str, Any]],
    ) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON field")
            result[key] = value
        return result

    path = Path(path_value)
    descriptor: int | None = None
    try:
        flags = os.O_RDONLY
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NONBLOCK"):
            flags |= os.O_NONBLOCK
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(path, flags)
        path_stat = os.fstat(descriptor)
        if (
            not stat.S_ISREG(path_stat.st_mode)
            or path_stat.st_uid != os.getuid()
            or path_stat.st_size > 64 * 1024
        ):
            raise HerdrPuppetError(
                "invalid_claude_hook_receipt_file",
                "The Claude hook receipt must be one caller-owned bounded regular file.",
            )
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            encoded = stream.read((64 * 1024) + 1)
        if len(encoded) > 64 * 1024:
            raise HerdrPuppetError(
                "invalid_claude_hook_receipt_file",
                "The Claude hook receipt must be one caller-owned bounded regular file.",
            )
        payload = json.loads(
            encoded.decode("utf-8"),
            object_pairs_hook=reject_duplicate_fields,
        )
    except HerdrPuppetError:
        raise
    except (
        OSError,
        UnicodeDecodeError,
        ValueError,
        RecursionError,
    ) as exc:
        raise HerdrPuppetError(
            "invalid_claude_hook_receipt_file",
            "The Claude hook receipt file is unavailable or malformed.",
        ) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
    if not isinstance(payload, dict):
        raise HerdrPuppetError(
            "invalid_claude_hook_receipt_file",
            "The Claude hook receipt must contain one JSON object.",
        )
    return payload


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
    destination = plan_parser.add_mutually_exclusive_group(required=True)
    destination.add_argument("--machine")
    destination.add_argument("--workspace-id")
    plan_parser.add_argument("--destination-catalog-json")
    plan_parser.add_argument("--workspace-label")
    plan_parser.add_argument("--expected-ssh-target")
    plan_parser.add_argument("--run-id", required=True)
    plan_parser.add_argument(
        "--harness",
        choices=CANONICAL_HARNESSES,
        required=True,
    )
    plan_parser.add_argument("--repo", required=True)
    plan_parser.add_argument("--worktree", required=True)
    plan_parser.add_argument("--proof-root", required=True)
    plan_parser.add_argument("--harness-binding-json", required=True)
    ordinal = plan_parser.add_mutually_exclusive_group()
    ordinal.add_argument(
        "--tab-ordinal",
        type=int,
        help="ordinal for one new tab; never selects an existing tab",
    )
    ordinal.add_argument(
        "--ordinal",
        type=int,
        help="deprecated alias for --tab-ordinal",
    )
    plan_parser.add_argument("--live-mutation-authorized", action="store_true")
    plan_parser.add_argument("--facts-json")
    plan_parser.add_argument("--output", required=True)
    _common_live(plan_parser)

    binding = subparsers.add_parser("harness-binding-create")
    binding.add_argument("--census-json", required=True)
    binding.add_argument("--repo", required=True)
    binding.add_argument("--output", required=True)

    recensus = subparsers.add_parser("harness-census-verify")
    recensus.add_argument("--lease-json", required=True)
    recensus.add_argument("--harness-binding-json", required=True)
    recensus.add_argument("--census-json", required=True)
    recensus.add_argument("--run-root", required=True)

    wrapper = subparsers.add_parser("instruction-wrapper-create")
    wrapper.add_argument("--harness-binding-json", required=True)
    wrapper.add_argument("--run-id", required=True)
    wrapper.add_argument("--task-file", required=True)
    wrapper.add_argument("--prompt-output", required=True)
    wrapper.add_argument("--manifest-output", required=True)

    status_parser = subparsers.add_parser("status")
    record = status_parser.add_mutually_exclusive_group(required=True)
    record.add_argument("--plan-json")
    record.add_argument("--lease-json")
    _common_live(status_parser)

    migrate_lease = subparsers.add_parser("lease-migrate")
    migrate_lease.add_argument("--lease-json", required=True)
    migrate_lease_v1 = subparsers.add_parser("lease-migrate-v1")
    migrate_lease_v1.add_argument("--lease-json", required=True)

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
    run_command.add_argument("--run-root", required=True)
    run_command.add_argument("--allow-live-qualification", action="store_true")
    _common_live(run_command)

    harness_launch = subparsers.add_parser("qualification-harness-launch")
    harness_launch.add_argument("--lease-json", required=True)
    harness_launch.add_argument("--seq", type=int, required=True)
    harness_launch.add_argument("--run-root", required=True)
    harness_launch.add_argument(
        "--allow-live-qualification",
        action="store_true",
    )
    _common_live(harness_launch)

    startup_gate = subparsers.add_parser("qualification-startup-gate")
    startup_gate.add_argument("--lease-json", required=True)
    startup_gate.add_argument("--seq", type=int, required=True)
    startup_gate.add_argument("--gate", required=True)
    startup_gate.add_argument("--action", required=True)
    startup_gate.add_argument("--source-worktree", required=True)
    startup_gate.add_argument("--operator-id", required=True)
    startup_gate.add_argument(
        "--evidence",
        choices=["operator_observed_exact_gate"],
        required=True,
    )
    startup_gate.add_argument("--confirm-exact-worktree", action="store_true")
    startup_gate.add_argument("--confirm-unrestricted", action="store_true")
    startup_gate.add_argument("--run-root", required=True)
    startup_gate.add_argument(
        "--allow-live-qualification",
        action="store_true",
    )
    _common_live(startup_gate)

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

    claude_lifecycle = subparsers.add_parser(
        "qualification-claude-lifecycle-observe"
    )
    claude_lifecycle.add_argument("--lease-json", required=True)
    claude_lifecycle.add_argument("--receipt-json", required=True)
    claude_lifecycle.add_argument(
        "--phase",
        choices=["armed", "initial", "steering"],
        required=True,
    )
    claude_lifecycle.add_argument("--run-root", required=True)

    claude_receipt_command = subparsers.add_parser(
        "qualification-claude-receipt-command"
    )
    claude_receipt_command.add_argument("--lease-json", required=True)

    send = subparsers.add_parser("qualification-send")
    send.add_argument("--lease-json", required=True)
    send.add_argument("--seq", type=int, required=True)
    send_source = send.add_mutually_exclusive_group(required=True)
    send_source.add_argument("--text-file")
    send_source.add_argument("--stdin", action="store_true", dest="prompt_stdin")
    send.add_argument("--run-root", required=True)
    send.add_argument("--instruction-manifest-json")
    send.add_argument("--checkpoint-nonce")
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
    reconcile.add_argument("--run-root", required=True)
    _common_live(reconcile)

    probe = subparsers.add_parser("qualification-token-probe")
    probe.add_argument("--lease-json", required=True)
    probe.add_argument("--nonce", required=True)
    probe.add_argument("--lines", type=int, default=40)
    probe.add_argument("--timeout-ms", type=int, default=30_000)
    probe.add_argument("--run-root", required=True)
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

    view_begin = subparsers.add_parser("qualification-view-begin")
    view_begin.add_argument("--lease-json", required=True)
    view_begin.add_argument("--nonce", required=True)
    view_begin.add_argument("--operator-id", required=True)
    view_begin.add_argument(
        "--confirm-native-tui-visible",
        action="store_true",
    )
    view_begin.add_argument("--run-root", required=True)
    view_begin.add_argument(
        "--allow-live-qualification",
        action="store_true",
    )
    _common_live(view_begin)

    view_complete = subparsers.add_parser("qualification-view-complete")
    view_complete.add_argument("--lease-json", required=True)
    view_complete.add_argument("--nonce", required=True)
    view_complete.add_argument("--operator-id", required=True)
    view_complete.add_argument(
        "--evidence",
        choices=["operator_observed_real_client_detach_reattach"],
        required=True,
    )
    view_complete.add_argument(
        "--confirm-detached-reattached",
        action="store_true",
    )
    view_complete.add_argument("--run-root", required=True)
    view_complete.add_argument(
        "--allow-live-qualification",
        action="store_true",
    )
    _common_live(view_complete)

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

    resume = subparsers.add_parser("lease-resume")
    resume.add_argument("--lease-json", required=True)
    resume.add_argument("--run-root", required=True)
    resume.add_argument("--allow-live-qualification", action="store_true")
    _common_live(resume, default_timeout_seconds=60.0)

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
            machine=args.machine,
            destination_catalog=(
                load_destination_catalog(args.destination_catalog_json)
                if args.destination_catalog_json
                else None
            ),
            run_id=args.run_id,
            harness=args.harness,
            repo=args.repo,
            worktree=args.worktree,
            proof_root=args.proof_root,
            harness_binding=load_json(args.harness_binding_json),
            tab_ordinal=args.tab_ordinal,
            ordinal=args.ordinal,
            live_mutation_authorized=args.live_mutation_authorized,
            facts=facts,
        )
        output = Path(args.output)
        if output.exists():
            raise HerdrPuppetError(
                "plan_output_exists",
                "Refusing to overwrite an existing plan output.",
                details={"output": str(output)},
            )
        write_create_only(
            output,
            (
                json.dumps(payload, indent=2, sort_keys=True) + "\n"
            ).encode("utf-8"),
        )
        return plan_selection_receipt(payload)
    if args.command == "harness-binding-create":
        binding = build_harness_binding(
            load_json(args.census_json),
            repo=args.repo,
        )
        write_create_only(
            Path(args.output),
            (
                json.dumps(
                    binding,
                    indent=2,
                    sort_keys=True,
                    ensure_ascii=False,
                )
                + "\n"
            ).encode("utf-8"),
        )
        return {
            "schema": "herdr-puppet.harness-binding-create.v1",
            "result": "ok",
            "harness": binding["harness"],
            "fingerprint": binding["fingerprint"],
            "profile_route": binding["profile"]["route"],
            "profile_enrollment": binding["profile"]["enrollment_state"],
            "explicit_model_selector": binding["regular_launch"][
                "explicit_model_selector"
            ],
            "observed_model": binding["model_observation"]["model"],
            "observed_effort": binding["model_observation"]["effort"],
            "launch_vector_sha256": binding["regular_launch"][
                "vector_sha256"
            ],
            "lifecycle_strategy": binding["lifecycle_observation"][
                "strategy"
            ],
            "instruction_plane": binding["instructions"]["plane"],
            "remote_harness_pid": "unavailable",
            "targeted_halt": "unsupported",
            "recovery": "unsupported",
            "crash_persistence": "unsupported",
            "raw_output_retained": False,
        }
    if args.command == "harness-census-verify":
        lease = load_json(args.lease_json)
        binding = load_json(args.harness_binding_json)
        if lease.get("harness_binding") != binding:
            raise HerdrPuppetError(
                "harness_binding_mismatch",
                "The census binding must exactly match the leased binding.",
            )
        return qualification_harness_census_verify(
            lease_payload=lease,
            lease_path=Path(args.lease_json),
            census=load_json(args.census_json),
            run_root=Path(args.run_root),
        )
    if args.command == "instruction-wrapper-create":
        task = _read_prompt(
            text_file=args.task_file,
            prompt_stdin=False,
        )
        rendered, manifest = compile_instruction_wrapper(
            binding_value=load_json(args.harness_binding_json),
            run_id=args.run_id,
            task=task,
        )
        write_create_only(Path(args.prompt_output), rendered)
        write_create_only(
            Path(args.manifest_output),
            (
                json.dumps(
                    manifest,
                    indent=2,
                    sort_keys=True,
                    ensure_ascii=False,
                )
                + "\n"
            ).encode("utf-8"),
        )
        return {
            "schema": "herdr-puppet.instruction-wrapper-create.v1",
            "result": "ok",
            "harness": manifest["harness"],
            "run_id": manifest["run_id"],
            "binding_fingerprint": manifest["binding_fingerprint"],
            "plane": manifest["plane"],
            "policy_fingerprint": manifest["policy_fingerprint"],
            "rendered_sha256": manifest["rendered_sha256"],
            "byte_count": manifest["byte_count"],
            "task_body_retained": False,
        }
    if args.command == "status":
        return structural_status(
            _client(args),
            plan_payload=load_json(args.plan_json) if args.plan_json else None,
            lease_payload=load_json(args.lease_json) if args.lease_json else None,
        )
    if args.command in {"lease-migrate", "lease-migrate-v1"}:
        lease_payload = load_json(args.lease_json)
        if (
            args.command == "lease-migrate-v1"
            and lease_payload.get("schema")
            not in {
                "herdr-puppet.lease.v1",
                "herdr-puppet.lease.v3",
            }
        ):
            raise HerdrPuppetError(
                "lease_migrate_v1_wrong_source",
                "The compatibility alias lease-migrate-v1 accepts a frozen "
                "lease-v1 source or its already-active lease-v3 result; use "
                "lease-migrate for lease-v2.",
            )
        return migrate_legacy_lease_file(
            lease_payload=lease_payload,
            lease_path=Path(args.lease_json),
            receipt_schema=(
                "herdr-puppet.lease-migrate-v1.v1"
                if args.command == "lease-migrate-v1"
                else "herdr-puppet.lease-migrate.v1"
            ),
        )
    if args.command == "journal-init":
        return initialize_journal(Path(args.run_root), load_json(args.plan_json))
    if args.command == "journal-append":
        if args.kind.startswith(("journal.", "qualification.")):
            raise HerdrPuppetError(
                "controller_event_kind_reserved",
                "Generic journal append cannot create controller-owned events.",
            )
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
            run_root=Path(args.run_root),
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
            run_root=Path(args.run_root),
            allow_live=args.allow_live_qualification,
        )
    if args.command == "qualification-harness-launch":
        return qualification_harness_launch(
            _client(args),
            lease_payload=load_json(args.lease_json),
            lease_path=Path(args.lease_json),
            seq=args.seq,
            run_root=Path(args.run_root),
            allow_live=args.allow_live_qualification,
        )
    if args.command == "qualification-startup-gate":
        return qualification_startup_gate(
            _client(args),
            lease_payload=load_json(args.lease_json),
            lease_path=Path(args.lease_json),
            seq=args.seq,
            gate=args.gate,
            action=args.action,
            source_worktree=args.source_worktree,
            operator_id=args.operator_id,
            evidence=args.evidence,
            confirm_exact_worktree=args.confirm_exact_worktree,
            confirm_unrestricted=args.confirm_unrestricted,
            run_root=Path(args.run_root),
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
    if args.command == "qualification-claude-lifecycle-observe":
        return qualification_claude_lifecycle_observe(
            lease_payload=load_json(args.lease_json),
            lease_path=Path(args.lease_json),
            receipt=_load_bounded_receipt(args.receipt_json),
            phase=args.phase,
            run_root=Path(args.run_root),
        )
    if args.command == "qualification-claude-receipt-command":
        return qualification_claude_receipt_command(
            lease_payload=load_json(args.lease_json),
            lease_path=Path(args.lease_json),
        )
    if args.command == "qualification-send":
        text = _read_prompt(
            text_file=args.text_file,
            prompt_stdin=args.prompt_stdin,
        )
        instruction_manifest = (
            load_json(args.instruction_manifest_json)
            if args.instruction_manifest_json
            else None
        )
        return qualification_send(
            _client(args),
            lease_payload=load_json(args.lease_json),
            lease_path=Path(args.lease_json),
            seq=args.seq,
            text=text,
            text_file=args.text_file,
            instruction_manifest=instruction_manifest,
            run_root=Path(args.run_root),
            allow_live=args.allow_live_qualification,
            checkpoint_nonce=args.checkpoint_nonce,
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
            run_root=Path(args.run_root),
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
    if args.command == "qualification-view-begin":
        return qualification_view_begin(
            _client(args),
            lease_payload=load_json(args.lease_json),
            lease_path=Path(args.lease_json),
            nonce=args.nonce,
            operator_id=args.operator_id,
            confirm_native_tui_visible=args.confirm_native_tui_visible,
            run_root=Path(args.run_root),
            allow_live=args.allow_live_qualification,
        )
    if args.command == "qualification-view-complete":
        return qualification_view_complete(
            _client(args),
            lease_payload=load_json(args.lease_json),
            lease_path=Path(args.lease_json),
            nonce=args.nonce,
            operator_id=args.operator_id,
            evidence=args.evidence,
            confirm_detached_reattached=args.confirm_detached_reattached,
            run_root=Path(args.run_root),
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
    if args.command == "lease-resume":
        return resume_lease(
            lease_payload=load_json(args.lease_json),
            lease_path=Path(args.lease_json),
            client=_client(args),
            allow_live=args.allow_live_qualification,
            run_root=Path(args.run_root),
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
