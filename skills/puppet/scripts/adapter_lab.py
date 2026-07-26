#!/usr/bin/env python3
"""Zero-agent census and doctor-only adapter-manifest tooling."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

from puppet_lib.adapter_manifest import (
    AdapterManifest,
    BEHAVIOR_CAPABILITIES,
    PROBE_CAPABILITIES,
    verify_qualification_receipt,
)
from puppet_lib.agy_launch import require_agy_regular_launch_authority
from puppet_lib.authority import attest_qualification
from puppet_lib.census import (
    CENSUS_SCHEMA_VERSION,
    adapter_implementation_fingerprint,
    census_many,
    census_target,
)
from puppet_lib.errors import PuppetError, UnsupportedError, ValidationError
from puppet_lib.probe import PROBE_PROFILE, recover_probe, run_probe
from puppet_lib.claude_paired_qualification import (
    claude_qualified_mapping,
    create_claude_pair,
    observe_native_view,
)
from puppet_lib.registry import process_birth_identity
from puppet_lib.tmux import TmuxController
from puppet_lib.safety import (
    atomic_write_json,
    read_json,
    sha256_file,
)


def _targets(value: str):
    targets = [item.strip() for item in value.split(",") if item.strip()]
    allowed = {"agy", "cursor", "claude", "codex", "grok"}
    if not targets or len(set(targets)) != len(targets) or not set(targets) <= allowed:
        raise argparse.ArgumentTypeError(
            "targets must be unique allowlisted harness names"
        )
    return targets


def _census(args):
    bundle = census_many(args.targets, adapter_implementation_fingerprint())
    atomic_write_json(args.out, bundle)
    return {
        "ok": True,
        "zero_agent": True,
        "targets": args.targets,
        "out": str(args.out),
    }


def _scaffold(args):
    bundle = read_json(args.census, max_bytes=1024 * 1024)
    if not isinstance(bundle, dict):
        raise ValidationError("zero-agent census root must be an object")
    schema_version = bundle.get("schema_version")
    if schema_version == 1:
        raise UnsupportedError(
            "legacy zero-agent census lacks authoritative runtime execution identity"
        )
    if schema_version != CENSUS_SCHEMA_VERSION:
        raise ValidationError("unsupported zero-agent census schema")
    manifests = bundle.get("manifests")
    if bundle.get("zero_agent") is not True or not isinstance(manifests, dict):
        raise ValidationError("invalid zero-agent census bundle")
    args.out.mkdir(mode=0o700, parents=True, exist_ok=True)
    written = []
    for target, raw in sorted(manifests.items()):
        manifest = AdapterManifest.from_dict(raw)
        destination = args.out / (target + ".json")
        manifest.save(destination)
        written.append(str(destination))
    return {"ok": True, "doctor_only": True, "manifests": written}


def _probe(args):
    expected_goal = {
        "repository": args.goal_repository,
        "commit": args.goal_commit,
        "path": args.goal_path,
        "sha256": args.goal_sha256,
    }
    return run_probe(
        target=args.target,
        profile=args.profile,
        session_profile=args.session_profile,
        proof_root=args.proof_root,
        manifest_path=args.manifest,
        mapping_path=args.mapping,
        authorization_path=args.authorization,
        controller=args.controller,
        goal_repo=args.goal_repo,
        expected_campaign_id=args.campaign_id,
        expected_goal=expected_goal,
        subscription_profile_root=args.subscription_profile_root,
        plane_descriptor=args.plane_descriptor,
        paired_activation_receipt=args.paired_activation_receipt,
        timeout=args.timeout,
        halt_timeout=args.halt_timeout,
        run_id=args.run_id,
    )


def _recover(args):
    expected_goal = {
        "repository": args.goal_repository,
        "commit": args.goal_commit,
        "path": args.goal_path,
        "sha256": args.goal_sha256,
    }
    return recover_probe(
        target=args.target,
        proof_root=args.proof_root,
        manifest_path=args.manifest,
        mapping_path=args.mapping,
        authorization_path=args.authorization,
        controller=args.controller,
        goal_repo=args.goal_repo,
        expected_campaign_id=args.campaign_id,
        expected_goal=expected_goal,
        run_id=args.run_id,
        plane_descriptor=args.plane_descriptor,
        paired_activation_receipt=args.paired_activation_receipt,
        halt_timeout=args.halt_timeout,
    )


def _verified_receipt(path: Path):
    header = read_json(path, max_bytes=131072, reject_sensitive_fields=True)
    if header.get("schema") == "puppet.cursor-regular-qualification/v1":
        from puppet_lib.cursor_qualification import (
            verify_cursor_terminal_qualification,
        )

        return verify_cursor_terminal_qualification(path)
    run = verify_qualification_receipt(path)
    if run.get("capabilities") != list(PROBE_CAPABILITIES):
        raise ValidationError(
            "probe receipt does not cover the shared capability contract"
        )
    return run


def _verify(args):
    run = _verified_receipt(args.run)
    return {
        "ok": True,
        "result": run.get("result", run.get("terminal_state")),
        "target": run["target"],
        "session_profile": run["session_profile"],
    }


def _claude_candidate(manifest_path: Path, mapping_path: Path) -> AdapterManifest:
    base = AdapterManifest.from_path(manifest_path)
    if base.target != "claude" or not base.raw["doctor_only"]:
        raise ValidationError("Claude pair input must be a doctor-only Claude manifest")
    raw = copy.deepcopy(base.raw)
    raw["yolo_mapping"] = read_json(mapping_path, max_bytes=65536)
    candidate = AdapterManifest.from_dict(raw)
    implementation_fingerprint = adapter_implementation_fingerprint()
    observed = census_target("claude", implementation_fingerprint)
    for name in (
        "platform",
        "executable",
        "execution",
        "adapter_fingerprint",
        "protocol_fingerprint",
        "yolo_mapping",
    ):
        if observed.raw[name] != candidate.raw[name]:
            raise ValidationError(
                "Claude pair input differs from fresh zero-agent census: %s" % name
            )
    return candidate


def _observe_claude_view(args):
    return observe_native_view(
        proof_root=args.proof_root,
        run_id=args.run_id,
        tmux_factory=TmuxController,
        process_birth_fn=process_birth_identity,
    )


def _pair_claude(args):
    candidate = _claude_candidate(args.manifest, args.mapping)
    return create_claude_pair(
        activation_receipt_path=args.activation_receipt,
        control_receipt_path=args.control_receipt,
        verify_receipt_fn=verify_qualification_receipt,
        attest_receipt_fn=attest_qualification,
        current_manifest=candidate,
    )


def _qualify(args):
    base = AdapterManifest.from_path(args.manifest)
    if not base.raw["doctor_only"]:
        raise ValidationError("qualification input must be a doctor-only manifest")
    receipt_path = args.receipt.resolve(strict=True)
    receipt = _verified_receipt(receipt_path)
    if base.target == "agy":
        require_agy_regular_launch_authority(receipt.get("session_profile"))
    cursor_terminal = receipt.get("schema") == "puppet.cursor-regular-qualification/v1"
    if receipt.get("plane_activation") is not None:
        raise UnsupportedError(
            "activation lifecycle proof cannot qualify a live adapter without matched no-bleed evidence"
        )
    if base.target == "claude" and receipt.get("claude_pairing") is None:
        raise UnsupportedError(
            "ordinary Claude control proof cannot qualify without a controller-verified activation/control pair"
        )
    mapping = read_json(args.mapping, max_bytes=65536)
    if base.target == "cursor":
        if not cursor_terminal:
            raise UnsupportedError(
                "Cursor qualification requires the terminal paired control receipt"
            )
        from puppet_lib.cursor_qualification import cursor_qualified_mapping

        mapping = cursor_qualified_mapping(mapping)
    if base.target == "codex" and mapping.get("complete") is False:
        if receipt.get("workspace_isolation") is None:
            raise UnsupportedError(
                "Codex qualification requires terminal controller-verified workspace isolation"
            )
        from puppet_lib.codex_workspace_plane import codex_qualified_mapping

        mapping = codex_qualified_mapping(mapping)
    if base.target == "claude" and mapping.get("complete") is False:
        mapping = claude_qualified_mapping(mapping)
    if base.target == "grok":
        # Filesystem-only ordinary-control absence cannot promote Grok. Paired
        # subscription-backed runtime matched control is still required.
        from puppet_lib.grok_workspace_plane import require_grok_qualification_promotion

        require_grok_qualification_promotion()
    raw = copy.deepcopy(base.raw)
    raw["yolo_mapping"] = mapping
    raw["capabilities"] = {
        name: (
            "controller_verified" if name in receipt["capabilities"] else "unsupported"
        )
        for name in BEHAVIOR_CAPABILITIES
    }
    raw["doctor_only"] = False
    raw["qualification"] = {
        "receipt_path": str(receipt_path),
        "receipt_sha256": sha256_file(receipt_path, max_bytes=131072),
        "session_profile": receipt["session_profile"],
    }
    qualified = AdapterManifest.from_dict(raw)
    qualified.verify_qualification(
        expected_session_profile=receipt["session_profile"]
    )
    qualified.save(args.out)
    return {
        "ok": True,
        "target": qualified.target,
        "session_profile": receipt["session_profile"],
        "manifest_fingerprint": qualified.fingerprint,
        "out": str(args.out),
    }


def _cursor_pair(args):
    from puppet_lib.cursor_qualification import (
        build_cursor_terminal_qualification,
        verify_cursor_terminal_qualification,
    )

    if args.out.exists() or args.out.is_symlink():
        raise ValidationError("Cursor terminal receipt output already exists")
    result = build_cursor_terminal_qualification(
        activated_receipt_path=args.activated_receipt,
        ordinary_receipt_path=args.ordinary_receipt,
        native_view_path=args.native_view,
    )
    atomic_write_json(args.out, result)
    verify_cursor_terminal_qualification(args.out)
    return {
        "ok": True,
        "target": "cursor",
        "terminal_state": result["terminal_state"],
        "out": str(args.out),
    }


def _cursor_request(args):
    from puppet_lib.cursor_qualification import build_cursor_qualification_request

    manifest = AdapterManifest.from_path(args.manifest)
    if (
        manifest.target != "cursor"
        or not manifest.raw["doctor_only"]
        or manifest.raw["qualification"] is not None
    ):
        raise ValidationError(
            "Cursor qualification request requires a fresh doctor-only manifest"
        )
    if args.out.exists() or args.out.is_symlink():
        raise ValidationError("Cursor qualification request output already exists")
    request = build_cursor_qualification_request(
        adapter_manifest_sha256=manifest.fingerprint
    )
    atomic_write_json(args.out, request)
    return {
        "ok": True,
        "target": "cursor",
        "authority": "request_only",
        "out": str(args.out),
    }


def _cursor_native_view(args):
    from puppet_lib.cursor_qualification import record_cursor_native_view

    state = read_json(
        args.run_root.resolve(strict=True) / "state.json",
        max_bytes=131072,
        reject_sensitive_fields=True,
    )
    attach_command = state.get("attach_command")
    if not isinstance(attach_command, str) or not attach_command:
        raise ValidationError("Cursor probe has not published its native attach command")
    print(
        json.dumps({"attach_command": attach_command}, sort_keys=True),
        file=sys.stderr,
        flush=True,
    )
    result = record_cursor_native_view(
        run_root=args.run_root,
        timeout=args.timeout,
    )
    return {
        "ok": True,
        "target": "cursor",
        "run_id": result["run_id"],
        "attached": result["attached"],
        "detached": result["detached"],
        "receipt": str(args.run_root.resolve() / "cursor-native-view.json"),
    }


def build_parser():
    parser = argparse.ArgumentParser(
        description="Build fingerprinted doctor-only Puppet adapter manifests without launching agents."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    census_parser = commands.add_parser("census")
    census_parser.add_argument("--targets", required=True, type=_targets)
    census_parser.add_argument("--out", required=True, type=Path)
    census_parser.set_defaults(handler=_census)
    scaffold_parser = commands.add_parser("scaffold")
    scaffold_parser.add_argument("--census", required=True, type=Path)
    scaffold_parser.add_argument("--out", required=True, type=Path)
    scaffold_parser.set_defaults(handler=_scaffold)
    probe_parser = commands.add_parser("probe")
    probe_parser.add_argument("--target", required=True)
    probe_parser.add_argument("--profile", required=True, choices=[PROBE_PROFILE])
    probe_parser.add_argument("--session-profile", required=True)
    probe_parser.add_argument("--proof-root", required=True, type=Path)
    probe_parser.add_argument("--manifest", required=True, type=Path)
    probe_parser.add_argument("--mapping", required=True, type=Path)
    probe_parser.add_argument("--authorization", required=True, type=Path)
    probe_parser.add_argument("--controller", required=True)
    probe_parser.add_argument("--campaign-id", required=True)
    probe_parser.add_argument("--goal-repo", required=True, type=Path)
    probe_parser.add_argument("--goal-repository", required=True)
    probe_parser.add_argument("--goal-commit", required=True)
    probe_parser.add_argument("--goal-path", required=True)
    probe_parser.add_argument("--goal-sha256", required=True)
    probe_parser.add_argument("--timeout", type=float, default=300.0)
    probe_parser.add_argument("--halt-timeout", type=float, default=10.0)
    probe_parser.add_argument("--run-id")
    probe_parser.add_argument(
        "--subscription-profile-root",
        type=Path,
        help=(
            "exact authenticated Puppet-owned private profile (required for non-AGY probes)"
        ),
    )
    probe_parser.add_argument("--plane-descriptor", type=Path)
    probe_parser.add_argument(
        "--paired-activation-receipt",
        type=Path,
        help=(
            "accepted activation-only Claude receipt that authorizes this ordinary control"
        ),
    )
    probe_parser.set_defaults(handler=_probe)
    recover_parser = commands.add_parser(
        "recover",
        help="reconcile one persisted probe by exact identity without relaunch",
    )
    recover_parser.add_argument("--target", required=True)
    recover_parser.add_argument("--proof-root", required=True, type=Path)
    recover_parser.add_argument("--manifest", required=True, type=Path)
    recover_parser.add_argument("--mapping", required=True, type=Path)
    recover_parser.add_argument("--authorization", required=True, type=Path)
    recover_parser.add_argument("--controller", required=True)
    recover_parser.add_argument("--campaign-id", required=True)
    recover_parser.add_argument("--goal-repo", required=True, type=Path)
    recover_parser.add_argument("--goal-repository", required=True)
    recover_parser.add_argument("--goal-commit", required=True)
    recover_parser.add_argument("--goal-path", required=True)
    recover_parser.add_argument("--goal-sha256", required=True)
    recover_parser.add_argument("--run-id", required=True)
    recover_parser.add_argument("--halt-timeout", type=float, default=10.0)
    recover_parser.add_argument("--plane-descriptor", type=Path)
    recover_parser.add_argument("--paired-activation-receipt", type=Path)
    recover_parser.set_defaults(handler=_recover)
    observe_parser = commands.add_parser(
        "observe-claude-view",
        help="record one live read-only Claude tmux client without pane capture",
    )
    observe_parser.add_argument("--proof-root", required=True, type=Path)
    observe_parser.add_argument("--run-id", required=True)
    observe_parser.set_defaults(handler=_observe_claude_view)
    pair_parser = commands.add_parser(
        "pair-claude",
        help="attest one terminal activation/control pair after no-bleed verification",
    )
    pair_parser.add_argument("--manifest", required=True, type=Path)
    pair_parser.add_argument("--mapping", required=True, type=Path)
    pair_parser.add_argument("--activation-receipt", required=True, type=Path)
    pair_parser.add_argument("--control-receipt", required=True, type=Path)
    pair_parser.set_defaults(handler=_pair_claude)
    verify_parser = commands.add_parser("verify")
    verify_parser.add_argument("--run", required=True, type=Path)
    verify_parser.set_defaults(handler=_verify)
    qualify_parser = commands.add_parser(
        "qualify",
        help="bind an accepted real-harness receipt to a doctor-only manifest",
    )
    qualify_parser.add_argument("--manifest", required=True, type=Path)
    qualify_parser.add_argument("--mapping", required=True, type=Path)
    qualify_parser.add_argument("--receipt", required=True, type=Path)
    qualify_parser.add_argument("--out", required=True, type=Path)
    qualify_parser.set_defaults(handler=_qualify)
    pair_parser = commands.add_parser(
        "cursor-pair",
        help="join activated/control Pass B and native-view proof into one terminal Cursor receipt",
    )
    pair_parser.add_argument("--activated-receipt", required=True, type=Path)
    pair_parser.add_argument("--ordinary-receipt", required=True, type=Path)
    pair_parser.add_argument("--native-view", required=True, type=Path)
    pair_parser.add_argument("--out", required=True, type=Path)
    pair_parser.set_defaults(handler=_cursor_pair)
    request_parser = commands.add_parser(
        "cursor-request",
        help="build a body-free activation request from a fresh Cursor doctor manifest",
    )
    request_parser.add_argument("--manifest", required=True, type=Path)
    request_parser.add_argument("--out", required=True, type=Path)
    request_parser.set_defaults(handler=_cursor_request)
    view_parser = commands.add_parser(
        "cursor-native-view",
        help="observe one human read-only native Cursor TUI attach and detach",
    )
    view_parser.add_argument("--run-root", required=True, type=Path)
    view_parser.add_argument("--timeout", type=float, default=120.0)
    view_parser.set_defaults(handler=_cursor_native_view)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        result = args.handler(args)
    except UnsupportedError as exc:
        print(json.dumps(exc.as_dict(), sort_keys=True), file=sys.stderr)
        return 3
    except PuppetError as exc:
        print(json.dumps(exc.as_dict(), sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
