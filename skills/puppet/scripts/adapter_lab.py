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
from puppet_lib.census import (
    CENSUS_SCHEMA_VERSION,
    adapter_implementation_fingerprint,
    census_many,
)
from puppet_lib.errors import PuppetError, UnsupportedError, ValidationError
from puppet_lib.probe import PROBE_PROFILE, recover_probe, run_probe
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
        halt_timeout=args.halt_timeout,
    )


def _verified_receipt(path: Path):
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
        "result": run["result"],
        "target": run["target"],
        "session_profile": run["session_profile"],
    }


def _qualify(args):
    base = AdapterManifest.from_path(args.manifest)
    if not base.raw["doctor_only"]:
        raise ValidationError("qualification input must be a doctor-only manifest")
    mapping = read_json(args.mapping, max_bytes=65536)
    receipt_path = args.receipt.resolve(strict=True)
    receipt = _verified_receipt(receipt_path)
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
    qualified.verify_qualification()
    qualified.save(args.out)
    return {
        "ok": True,
        "target": qualified.target,
        "session_profile": receipt["session_profile"],
        "manifest_fingerprint": qualified.fingerprint,
        "out": str(args.out),
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
    recover_parser.set_defaults(handler=_recover)
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
