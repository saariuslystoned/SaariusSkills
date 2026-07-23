#!/usr/bin/env python3
"""Puppet bootstrap CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from puppet_lib.errors import PuppetError, UnsupportedError, ValidationError
from puppet_lib.promotions import close_bootstrap, promote_bootstrap
from puppet_lib.session import (
    accept_checkpoint,
    attach_command,
    doctor,
    halt,
    import_checkpoint,
    launch,
    open_view,
    review_checkpoint,
    send_message,
    status,
    wait_for,
)
from puppet_lib.subscription_profiles import (
    initialize_subscription_profile,
    subscription_profile_status,
)


def _path(value: str) -> Path:
    return Path(value)


def _doctor(args):
    return doctor(
        contract_path=args.contract,
        manifest_path=args.manifest,
        authorization_path=args.authorization,
        proof_root=args.proof_root,
        state_root=args.state_root,
    )


def _launch(args):
    if args.prompt_file.is_symlink() or not args.prompt_file.is_file():
        raise ValidationError("prompt file must be a regular non-symlink file")
    prompt = args.prompt_file.read_text(encoding="utf-8")
    return launch(
        session=args.session,
        contract_path=args.contract,
        manifest_path=args.manifest,
        authorization_path=args.authorization,
        proof_root=args.proof_root,
        state_root=args.state_root,
        supervisor_executable=Path(__file__),
        prompt=prompt,
        requested_model=args.model,
        requested_effort=args.effort,
    )


def _send(args):
    if args.stdin:
        message = sys.stdin.read()
    else:
        if args.message_file.is_symlink() or not args.message_file.is_file():
            raise ValidationError("message file must be a regular non-symlink file")
        message = args.message_file.read_text(encoding="utf-8")
    return send_message(
        state_root=args.state_root,
        session=args.session,
        message=message,
        request_id=args.request_id,
    )


def _status(args):
    return status(state_root=args.state_root, session=args.session)


def _wait(args):
    return wait_for(
        state_root=args.state_root,
        session=args.session,
        condition=args.until,
        timeout=args.timeout,
    )


def _checkpoint(args):
    return import_checkpoint(
        state_root=args.state_root, session=args.session, handoff_path=args.handoff
    )


def _review(args):
    return review_checkpoint(
        state_root=args.state_root,
        session=args.session,
        checkpoint_id=args.checkpoint,
        actor=args.actor,
        verdict=args.verdict,
        evidence_path=args.evidence,
    )


def _accept(args):
    return accept_checkpoint(
        state_root=args.state_root,
        session=args.session,
        checkpoint_id=args.checkpoint,
        actor=args.actor,
        evidence_path=args.evidence,
    )


def _attach(args):
    return attach_command(state_root=args.state_root, session=args.session)


def _open_view(args):
    return open_view(
        state_root=args.state_root,
        session=args.session,
        terminal=args.terminal,
        dry_run=args.dry_run,
    )


def _halt(args):
    return halt(
        state_root=args.state_root,
        session=args.session,
        timeout=args.timeout,
    )


def _profile_init(args):
    return initialize_subscription_profile(
        target=args.target,
        profile_root=args.profile_root,
        executable_path=args.executable,
    )


def _profile_status(args):
    return subscription_profile_status(profile_root=args.profile_root)


def _promote(args):
    return promote_bootstrap()


def _close(args):
    return close_bootstrap()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="puppet",
        description=(
            "YOLO-only transcript-blind lifecycle control for bounded agent sessions. "
            "Prompted or sandboxed live operation is unsupported."
        ),
    )
    parser.add_argument(
        "--json",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Emit JSON output (JSON is the default).",
    )
    parser.add_argument("--version", action="version", version="puppet 0.1.0-bootstrap")
    commands = parser.add_subparsers(dest="command", required=True)

    doctor_parser = commands.add_parser("doctor", help="run read-only preflight")
    doctor_parser.add_argument("--contract", required=True, type=_path)
    doctor_parser.add_argument("--manifest", required=True, type=_path)
    doctor_parser.add_argument("--authorization", required=True, type=_path)
    doctor_parser.add_argument("--proof-root", required=True, type=_path)
    doctor_parser.add_argument("--state-root", required=True, type=_path)
    doctor_parser.set_defaults(handler=_doctor)

    launch_parser = commands.add_parser("launch", help="launch a verified target")
    launch_parser.add_argument("--session", required=True)
    launch_parser.add_argument("--contract", required=True, type=_path)
    launch_parser.add_argument("--manifest", required=True, type=_path)
    launch_parser.add_argument("--authorization", required=True, type=_path)
    launch_parser.add_argument("--proof-root", required=True, type=_path)
    launch_parser.add_argument("--state-root", required=True, type=_path)
    launch_parser.add_argument("--prompt-file", required=True, type=_path)
    launch_parser.add_argument("--model")
    launch_parser.add_argument("--effort")
    launch_parser.set_defaults(handler=_launch)

    send_parser = commands.add_parser("send", help="send one literal bounded message")
    send_parser.add_argument("--state-root", required=True, type=_path)
    send_parser.add_argument("--session", required=True)
    send_parser.add_argument("--request-id", required=True)
    send_input = send_parser.add_mutually_exclusive_group(required=True)
    send_input.add_argument("--message-file", type=_path)
    send_input.add_argument(
        "--stdin", action="store_true", help="read message body from stdin"
    )
    send_parser.set_defaults(handler=_send)

    status_parser = commands.add_parser(
        "status", help="show sanitized structural state"
    )
    status_parser.add_argument("--state-root", required=True, type=_path)
    status_parser.add_argument("--session", required=True)
    status_parser.set_defaults(handler=_status)

    wait_parser = commands.add_parser("wait", help="wait for one bounded condition")
    wait_parser.add_argument("--state-root", required=True, type=_path)
    wait_parser.add_argument("--session", required=True)
    wait_parser.add_argument(
        "--until",
        required=True,
        choices=["checkpoint", "beacon", "action-required", "target-stopped", "done"],
    )
    wait_parser.add_argument("--timeout", required=True, type=float)
    wait_parser.set_defaults(handler=_wait)

    checkpoint_parser = commands.add_parser("checkpoint", help="validate one handoff")
    checkpoint_parser.add_argument("--state-root", required=True, type=_path)
    checkpoint_parser.add_argument("--session", required=True)
    checkpoint_parser.add_argument("--handoff", required=True, type=_path)
    checkpoint_parser.set_defaults(handler=_checkpoint)

    review_parser = commands.add_parser("review", help="record a controller verdict")
    review_parser.add_argument("--state-root", required=True, type=_path)
    review_parser.add_argument("--session", required=True)
    review_parser.add_argument("--actor", required=True)
    review_parser.add_argument("--checkpoint", required=True)
    review_parser.add_argument(
        "--verdict",
        required=True,
        choices=["repair", "conformance_accept", "source_accept", "block", "fail"],
    )
    review_parser.add_argument("--evidence", required=True, type=_path)
    review_parser.set_defaults(handler=_review)

    accept_parser = commands.add_parser(
        "accept", help="record terminal controller acceptance"
    )
    accept_parser.add_argument("--state-root", required=True, type=_path)
    accept_parser.add_argument("--session", required=True)
    accept_parser.add_argument("--actor", required=True)
    accept_parser.add_argument("--checkpoint", required=True)
    accept_parser.add_argument("--evidence", required=True, type=_path)
    accept_parser.set_defaults(handler=_accept)

    attach_parser = commands.add_parser(
        "attach-command", help="print a read-only viewer command"
    )
    attach_parser.add_argument("--state-root", required=True, type=_path)
    attach_parser.add_argument("--session", required=True)
    attach_parser.set_defaults(handler=_attach)

    view_parser = commands.add_parser(
        "open-view",
        help="optionally open the exact native TUI in a separate read-only terminal",
    )
    view_parser.add_argument("--state-root", required=True, type=_path)
    view_parser.add_argument("--session", required=True)
    view_parser.add_argument(
        "--terminal",
        choices=["auto", "iterm", "terminal"],
        default="auto",
    )
    view_parser.add_argument("--dry-run", action="store_true")
    view_parser.set_defaults(handler=_open_view)

    profile_init_parser = commands.add_parser(
        "profile-init",
        help="create a private subscription profile and print its human login handoff",
    )
    profile_init_parser.add_argument(
        "--target",
        required=True,
        choices=["agy", "codex", "claude", "cursor", "grok"],
    )
    profile_init_parser.add_argument("--profile-root", required=True, type=_path)
    profile_init_parser.add_argument("--executable", required=True, type=_path)
    profile_init_parser.set_defaults(handler=_profile_init)

    profile_status_parser = commands.add_parser(
        "profile-status",
        help="report body-free auth state for one private subscription profile",
    )
    profile_status_parser.add_argument("--profile-root", required=True, type=_path)
    profile_status_parser.set_defaults(handler=_profile_status)

    halt_parser = commands.add_parser(
        "halt", help="gracefully halt only the registered target"
    )
    halt_parser.add_argument("--state-root", required=True, type=_path)
    halt_parser.add_argument("--session", required=True)
    halt_parser.add_argument("--timeout", type=float, default=10.0)
    halt_parser.set_defaults(handler=_halt)

    promote_parser = commands.add_parser(
        "promote", help="unsupported in bootstrap Puppet N"
    )
    promote_parser.set_defaults(handler=_promote)
    close_parser = commands.add_parser(
        "close", help="unsupported in bootstrap Puppet N"
    )
    close_parser.set_defaults(handler=_close)
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = args.handler(args)
    except UnsupportedError as exc:
        print(json.dumps(exc.as_dict(), sort_keys=True), file=sys.stderr)
        return 3
    except PuppetError as exc:
        print(json.dumps(exc.as_dict(), sort_keys=True), file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
