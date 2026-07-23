from __future__ import annotations

import inspect
import json
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "puppet" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import adapter_lab as puppet_adapter_lab  # noqa: E402
from puppet_lib import adapter_manifest, probe, session  # noqa: E402
from puppet_lib.codex_launch import (  # noqa: E402
    DEFAULT_MODEL_CLASSIFICATION,
    DEFAULT_MODEL_SENTINEL,
    MAPPING_INCOMPLETE_BLOCKER,
    SOURCE_ONLY_BLOCKERS,
    CodexDoctorObservation,
)
from puppet_lib.errors import ConflictError, IdentityError, ValidationError  # noqa: E402
from puppet_lib.run_observations import (  # noqa: E402
    RUN_OBSERVATION_SCHEMA,
    UNAVAILABLE,
    ZERO_AGENT_CLAUDE_MATCHED_CONTROL_BLOCKER_KIND,
    build_claude_matched_control_blocker_observation,
    build_codex_doctor_run_observation,
    validate_claude_matched_control_blocker_observation,
    validate_codex_doctor_run_observation,
    write_claude_matched_control_blocker_observation,
    write_codex_doctor_run_observation,
)
from puppet_lib.safety import canonical_json_bytes, sha256_bytes  # noqa: E402


def observation() -> CodexDoctorObservation:
    return CodexDoctorObservation(
        classification=DEFAULT_MODEL_CLASSIFICATION,
        observed_model=DEFAULT_MODEL_SENTINEL,
        observed_provider="openai",
        doctor_output_sha256="1" * 64,
        doctor_output_bytes=123,
        manifest_fingerprint="2" * 64,
        execution_fingerprint="3" * 64,
        adapter_fingerprint="4" * 64,
        protocol_fingerprint="5" * 64,
        codex_home_identity_sha256="6" * 64,
        launch_context_sha256="7" * 64,
        doctor_command_identity={
            "cwd_sha256": "8" * 64,
            "argv_sha256": "9" * 64,
            "env_names": ["CODEX_HOME"],
            "env_fingerprint": "a" * 64,
            "admitted_lane_root_sha256": "b" * 64,
        },
        blockers=(*SOURCE_ONLY_BLOCKERS, MAPPING_INCOMPLETE_BLOCKER),
    )


def build(source: CodexDoctorObservation | None = None) -> dict:
    return build_codex_doctor_run_observation(
        observation() if source is None else source,
        run_id="codex-doctor-one",
        task_type="zero_agent_doctor",
        task_profile="regular_qualification",
        latency_milliseconds=321,
    )


def build_claude() -> dict:
    return build_claude_matched_control_blocker_observation(
        run_id="claude-source-gap-one",
        latency_milliseconds=17,
    )


class RunObservationTests(unittest.TestCase):
    def test_exact_body_free_zero_agent_record_is_deterministic(self):
        value = build()
        self.assertEqual(value, build())
        self.assertEqual(value["schema"], RUN_OBSERVATION_SCHEMA)
        self.assertEqual(value["requested_model"], "current_default")
        self.assertEqual(value["observed_model"], DEFAULT_MODEL_SENTINEL)
        self.assertEqual(value["observed_effort"], UNAVAILABLE)
        self.assertEqual(value["native_turn_count"], UNAVAILABLE)
        self.assertEqual(value["native_tool_call_count"], UNAVAILABLE)
        self.assertEqual(value["checkpoint_quality"], UNAVAILABLE)
        self.assertEqual(value["controller_verdict"], "blocked")
        self.assertEqual(value["repair_cycles"], 0)
        self.assertFalse(value["target_claimed_green"])
        self.assertFalse(value["controller_gates_green"])
        self.assertFalse(value["independent_review_clean"])
        self.assertFalse(value["launch_authorized"])
        self.assertFalse(value["model_selection_authorized"])
        self.assertFalse(value["qualification_authorized"])
        self.assertFalse(value["promotion_authorized"])
        encoded = json.dumps(value, sort_keys=True)
        self.assertNotIn("doctor_command_identity", encoded)
        self.assertNotIn("CODEX_HOME", encoded)
        self.assertNotIn("prompt", encoded.lower())

    def test_tampered_record_and_missing_metric_literals_fail_closed(self):
        source = observation()
        for field, replacement in (
            ("controller_verdict", "qualified"),
            ("native_turn_count", 0),
            ("checkpoint_quality", "good"),
            ("qualification_authorized", True),
        ):
            with self.subTest(field=field):
                value = build(source)
                value[field] = replacement
                core = dict(value)
                core.pop("record_sha256")
                value["record_sha256"] = sha256_bytes(canonical_json_bytes(core))
                with self.assertRaises((IdentityError, ValidationError)):
                    validate_codex_doctor_run_observation(
                        value,
                        source,
                        run_id="codex-doctor-one",
                        task_type="zero_agent_doctor",
                        task_profile="regular_qualification",
                        latency_milliseconds=321,
                    )

    def test_source_digest_target_and_authority_tampering_fail_closed(self):
        source = observation()
        for field, replacement in (
            ("observation_sha256", "0" * 64),
            ("target", "claude"),
            ("launch_authorized", True),
        ):
            with self.subTest(field=field):
                changed = source.to_public_dict()
                changed[field] = replacement
                if field != "observation_sha256":
                    core = dict(changed)
                    core.pop("observation_sha256")
                    changed["observation_sha256"] = sha256_bytes(
                        canonical_json_bytes(core)
                    )
                with (
                    mock.patch.object(
                        CodexDoctorObservation,
                        "to_public_dict",
                        return_value=changed,
                    ),
                    self.assertRaises((IdentityError, ValidationError)),
                ):
                    build(source)

    def test_path_traversal_latency_and_identity_inputs_are_rejected(self):
        source = observation()
        for run_id in ("../escape", "/absolute", "bad name"):
            with self.subTest(run_id=run_id):
                with self.assertRaises(ValidationError):
                    build_codex_doctor_run_observation(
                        source,
                        run_id=run_id,
                        task_type="zero_agent_doctor",
                        task_profile="regular_qualification",
                        latency_milliseconds=1,
                    )
        for latency in (-1, True, 3_600_001):
            with self.subTest(latency=latency):
                with self.assertRaises(ValidationError):
                    build_codex_doctor_run_observation(
                        source,
                        run_id="safe-run",
                        task_type="zero_agent_doctor",
                        task_profile="regular_qualification",
                        latency_milliseconds=latency,
                    )

    def test_atomic_create_only_record_preserves_first_observation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run-observations"
            root.mkdir(mode=0o700)
            root.chmod(0o700)
            source = observation()
            path = write_codex_doctor_run_observation(
                root,
                source,
                run_id="codex-doctor-one",
                task_type="zero_agent_doctor",
                task_profile="regular_qualification",
                latency_milliseconds=321,
            )
            before = path.read_bytes()
            self.assertEqual(
                json.loads(before),
                build(),
            )
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(
                [item.name for item in root.iterdir()],
                ["codex-doctor-one.json"],
            )
            with self.assertRaisesRegex(ConflictError, "already exists"):
                write_codex_doctor_run_observation(
                    root,
                    source,
                    run_id="codex-doctor-one",
                    task_type="zero_agent_doctor",
                    task_profile="regular_qualification",
                    latency_milliseconds=999,
                )
            self.assertEqual(path.read_bytes(), before)

    def test_private_root_and_runtime_consumers_remain_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run-observations"
            root.mkdir(mode=0o755)
            with self.assertRaisesRegex(IdentityError, "user-private"):
                write_codex_doctor_run_observation(
                    root,
                    observation(),
                    run_id="codex-doctor-one",
                    task_type="zero_agent_doctor",
                    task_profile="regular_qualification",
                    latency_milliseconds=1,
                )
        for module in (adapter_manifest, probe, session, puppet_adapter_lab):
            self.assertNotIn("run_observations", inspect.getsource(module))

    def test_claude_blocker_is_deterministic_body_free_and_non_authorizing(self):
        value = build_claude()
        self.assertEqual(value, build_claude())
        self.assertEqual(
            value["kind"],
            ZERO_AGENT_CLAUDE_MATCHED_CONTROL_BLOCKER_KIND,
        )
        self.assertEqual(value["requested_harness"], "claude")
        for name in (
            "observed_harness",
            "observed_version",
            "observed_model",
            "model_observation_classification",
            "observed_provider",
            "observed_effort",
            "native_turn_count",
            "native_tool_call_count",
            "checkpoint_quality",
            "exact_accepted_head",
        ):
            self.assertEqual(value[name], UNAVAILABLE)
        self.assertEqual(value["controller_verdict"], "blocked")
        self.assertEqual(value["proof_integrity"], "source_only")
        self.assertEqual(value["verification_depth"], "source_only")
        self.assertEqual(
            [item["role"] for item in value["source_bundle"]],
            [
                "activation_binding",
                "pre_delivery_authority",
                "signal_observation",
                "probe_integration",
                "terminal_verifier",
            ],
        )
        self.assertEqual(
            value["source_observation_sha256"],
            value["source_bundle_sha256"],
        )
        for name in (
            "target_claimed_green",
            "controller_gates_green",
            "independent_review_clean",
            "launch_authorized",
            "delivery_authorized",
            "checkpoint_observed",
            "no_bleed_evaluated",
            "no_bleed_verified",
            "model_selection_authorized",
            "qualification_authorized",
            "promotion_authorized",
        ):
            self.assertIs(value[name], False)
        encoded = json.dumps(value, sort_keys=True)
        for forbidden in (
            "PUPPET_CLAUDE_MATCHED_CONTROL_MARKER",
            ".puppet-claude-marker-signal",
            "WRITE_READY_JSON",
            "handoffs/",
            "prompt",
            "marker",
        ):
            self.assertNotIn(forbidden, encoded)

    def test_claude_blocker_rejects_tampering_and_source_drift(self):
        for field, replacement in (
            ("controller_verdict", "qualified"),
            ("observed_model", "<default>"),
            ("checkpoint_quality", "accepted"),
            ("delivery_authorized", True),
            ("no_bleed_verified", True),
            ("qualification_authorized", True),
            ("limitations", []),
        ):
            with self.subTest(field=field):
                value = build_claude()
                value[field] = replacement
                core = dict(value)
                core.pop("record_sha256")
                value["record_sha256"] = sha256_bytes(canonical_json_bytes(core))
                with self.assertRaises(IdentityError):
                    validate_claude_matched_control_blocker_observation(
                        value,
                        run_id="claude-source-gap-one",
                        latency_milliseconds=17,
                    )

        value = build_claude()
        with (
            mock.patch(
                "puppet_lib.run_observations.sha256_file",
                return_value="0" * 64,
            ),
            self.assertRaisesRegex(IdentityError, "current source bundle"),
        ):
            validate_claude_matched_control_blocker_observation(
                value,
                run_id="claude-source-gap-one",
                latency_milliseconds=17,
            )

    def test_claude_blocker_persistence_is_private_mode_0600_and_create_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run-observations"
            root.mkdir(mode=0o700)
            root.chmod(0o700)
            path = write_claude_matched_control_blocker_observation(
                root,
                run_id="claude-source-gap-one",
                latency_milliseconds=17,
            )
            before = path.read_bytes()
            self.assertEqual(json.loads(before), build_claude())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            with self.assertRaisesRegex(ConflictError, "already exists"):
                write_claude_matched_control_blocker_observation(
                    root,
                    run_id="claude-source-gap-one",
                    latency_milliseconds=18,
                )
            self.assertEqual(path.read_bytes(), before)

    def test_claude_blocker_rejects_invalid_run_and_latency(self):
        for run_id in ("../escape", "/absolute", "bad name"):
            with self.subTest(run_id=run_id):
                with self.assertRaises(ValidationError):
                    build_claude_matched_control_blocker_observation(
                        run_id=run_id,
                        latency_milliseconds=1,
                    )
        for latency in (-1, True, 3_600_001):
            with self.subTest(latency=latency):
                with self.assertRaises(ValidationError):
                    build_claude_matched_control_blocker_observation(
                        run_id="claude-source-gap-one",
                        latency_milliseconds=latency,
                    )


if __name__ == "__main__":
    unittest.main()
