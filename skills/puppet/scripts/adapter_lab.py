#!/usr/bin/env python3
"""Zero-agent census and doctor-only adapter-manifest tooling."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

from puppet_lib.adapter_manifest import AdapterManifest
from puppet_lib.census import census_many
from puppet_lib.errors import PuppetError, UnsupportedError, ValidationError
from puppet_lib.safety import (
    atomic_write_json,
    read_json,
    sha256_file,
    validate_identifier,
    validate_sha256,
)


def _targets(value: str):
    targets = [item.strip() for item in value.split(",") if item.strip()]
    allowed = {"agy", "cursor", "claude", "codex", "grok"}
    if not targets or len(set(targets)) != len(targets) or not set(targets) <= allowed:
        raise argparse.ArgumentTypeError("targets must be unique allowlisted harness names")
    return targets


def _census(args):
    adapter_source = Path(__file__).parent / "puppet_lib" / "adapters.py"
    bundle = census_many(args.targets, sha256_file(adapter_source))
    atomic_write_json(args.out, bundle)
    return {"ok": True, "zero_agent": True, "targets": args.targets, "out": str(args.out)}


def _scaffold(args):
    bundle = read_json(args.census, max_bytes=1024 * 1024)
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
    raise UnsupportedError(
        "real probe orchestration is unavailable until bootstrap Puppet N is sealed and directly tested"
    )


def _verify(args):
    run = read_json(args.run, max_bytes=131072, reject_sensitive_fields=True)
    required = {
        "schema_version",
        "run_id",
        "target",
        "result",
        "executable_fingerprint",
        "adapter_fingerprint",
        "protocol_fingerprint",
        "yolo_mapping_sha256",
        "controller",
        "kind",
        "capabilities",
        "accepted_checkpoint_id",
        "acceptance_sha256",
        "halt_receipt_sha256",
        "proof_refs",
    }
    if set(run) != required or run.get("schema_version") != 1:
        raise ValidationError("probe result fields do not match schema")
    if run.get("target") not in {"agy", "cursor", "claude", "codex", "grok"}:
        raise ValidationError("invalid probe target")
    if run.get("kind") != "real_harness_conformance":
        raise ValidationError("invalid probe receipt kind")
    if run.get("result") != "accepted":
        raise ValidationError("qualification receipt is not accepted")
    validate_identifier(run.get("run_id"), "run id")
    validate_identifier(run.get("controller"), "controller")
    for field in (
        "executable_fingerprint",
        "adapter_fingerprint",
        "protocol_fingerprint",
        "yolo_mapping_sha256",
        "accepted_checkpoint_id",
        "acceptance_sha256",
        "halt_receipt_sha256",
    ):
        validate_sha256(run.get(field), field)
    expected_capabilities = ["launch", "send", "status", "wait", "checkpoint", "resume", "halt"]
    if run.get("capabilities") != expected_capabilities:
        raise ValidationError("probe receipt does not cover the complete capability contract")
    if not isinstance(run.get("proof_refs"), list):
        raise ValidationError("probe proof references must be a list")
    return {"ok": True, "result": run["result"], "target": run["target"]}


def _qualify(args):
    base = AdapterManifest.from_path(args.manifest)
    if not base.raw["doctor_only"]:
        raise ValidationError("qualification input must be a doctor-only manifest")
    mapping = read_json(args.mapping, max_bytes=65536)
    receipt_path = args.receipt.resolve(strict=True)
    raw = copy.deepcopy(base.raw)
    raw["yolo_mapping"] = mapping
    raw["capabilities"] = {
        name: "controller_verified"
        for name in ("launch", "send", "status", "wait", "checkpoint", "resume", "halt")
    }
    raw["doctor_only"] = False
    raw["qualification"] = {
        "receipt_path": str(receipt_path),
        "receipt_sha256": sha256_file(receipt_path, max_bytes=131072),
    }
    qualified = AdapterManifest.from_dict(raw)
    qualified.verify_qualification()
    qualified.save(args.out)
    return {
        "ok": True,
        "target": qualified.target,
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
    probe_parser.add_argument("--profile", required=True)
    probe_parser.add_argument("--proof-root", required=True, type=Path)
    probe_parser.set_defaults(handler=_probe)
    verify_parser = commands.add_parser("verify")
    verify_parser.add_argument("--run", required=True, type=Path)
    verify_parser.set_defaults(handler=_verify)
    qualify_parser = commands.add_parser(
        "qualify", help="bind an accepted real-harness receipt to a doctor-only manifest"
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
