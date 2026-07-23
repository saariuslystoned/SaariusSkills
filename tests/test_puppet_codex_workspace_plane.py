from __future__ import annotations

import copy
import inspect
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "puppet" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from puppet_lib import codex_workspace_plane as workspace_module  # noqa: E402
from puppet_lib.adapter_manifest import QUALIFICATION_PROFILE  # noqa: E402
from puppet_lib.codex_launch import (  # noqa: E402
    AUTH_ROUTE,
    CURRENT_DEFAULT_SELECTION,
    EXPECTED_UNRESTRICTED_FLAG,
    MAPPING_INCOMPLETE_BLOCKER,
    SOURCE_ONLY_BLOCKERS,
    CodexLaunchContext,
)
from puppet_lib.codex_workspace_plane import (  # noqa: E402
    CodexWorkspacePlan,
    materialize_codex_workspace_plane,
    plan_codex_workspace_plane,
    recover_codex_workspace_plane,
    revalidate_codex_workspace_plan,
    rollback_codex_workspace_plane,
    verify_codex_workspace_plane,
)
from puppet_lib.conformance import tree_fingerprint  # noqa: E402
from puppet_lib.errors import (  # noqa: E402
    ConflictError,
    IdentityError,
    UnsupportedError,
    ValidationError,
)
from puppet_lib.instructions import compile_instruction_wrapper  # noqa: E402
from puppet_lib.safety import canonical_json_bytes, sha256_bytes  # noqa: E402


def _root_identity(path: Path) -> dict[str, object]:
    path = path.resolve(strict=True)
    details = path.lstat()
    return {
        "path": str(path),
        "device": details.st_dev,
        "inode": details.st_ino,
        "uid": details.st_uid,
        "gid": details.st_gid,
        "mode": stat.S_IMODE(details.st_mode),
        "nlink": details.st_nlink,
    }


class CodexWorkspacePlaneTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.lane = self.base / "lane"
        self.workspace = self.lane / "workspace"
        self.codex_home = self.lane / "codex-home"
        for path in (self.lane, self.workspace, self.codex_home):
            path.mkdir(mode=0o700)
            path.chmod(0o700)

        self.requested_executable = self.base / "bin" / "codex"
        self.resolved_executable = self.base / "install" / "codex-runtime"
        self.requested_executable.parent.mkdir()
        self.resolved_executable.parent.mkdir()
        self.resolved_executable.write_bytes(b"codex-runtime-fixture")
        self.requested_executable.symlink_to(self.resolved_executable)
        self.executable_sha256 = sha256_bytes(self.resolved_executable.read_bytes())
        self.version_sha256 = "2" * 64

        for name, value in (
            ("EXPECTED_REQUESTED_EXECUTABLE_PATH", str(self.requested_executable)),
            ("EXPECTED_RESOLVED_EXECUTABLE_PATH", str(self.resolved_executable)),
            ("EXPECTED_EXECUTABLE_SHA256", self.executable_sha256),
            ("EXPECTED_VERSION_SHA256", self.version_sha256),
        ):
            patcher = mock.patch.object(workspace_module, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

        self.expected_contract_identity = {
            "fingerprint": "3" * 64,
            "controller": "controller-a",
            "target": "codex",
            "task_profile": QUALIFICATION_PROFILE,
        }
        self.expected_run_identity = {
            "session": "codex-session-a",
            "run_id": "codex-run-a",
            "nonce": "codex-nonce-a",
        }
        self.compiled = compile_instruction_wrapper(
            target="codex",
            task="PUPPET_INSTRUCTION_BODY_CANARY must never persist in the plan",
            contract_identity=self.expected_contract_identity,
            workspace_identity={
                "fixture_fingerprint": tree_fingerprint(self.workspace),
                "workspace": "isolated_conformance_fixture",
            },
            run_identity=self.expected_run_identity,
            model_binding="default",
            effort_binding="default",
        )
        self.context = self._context()

    def _context(self, **overrides) -> CodexLaunchContext:
        values = {
            "target": "codex",
            "session_profile": "regular",
            "manifest_fingerprint": "5" * 64,
            "adapter_fingerprint": "6" * 64,
            "protocol_fingerprint": "7" * 64,
            "version_text": workspace_module.EXPECTED_VERSION_TEXT,
            "requested_executable_path": str(self.requested_executable),
            "resolved_executable_path": str(self.resolved_executable),
            "manifest_executable_sha256": self.executable_sha256,
            "manifest_version_sha256": self.version_sha256,
            "model_selection": CURRENT_DEFAULT_SELECTION,
            "effort_selection": CURRENT_DEFAULT_SELECTION,
            "lane_root_identity": _root_identity(self.lane),
            "workspace_root_identity": _root_identity(self.workspace),
            "codex_home_identity": _root_identity(self.codex_home),
            "launch_authorized": False,
            "blockers": (*SOURCE_ONLY_BLOCKERS, MAPPING_INCOMPLETE_BLOCKER),
            "auth_route": AUTH_ROUTE,
            "candidate_process_count": 0,
            "candidate_process_pids": (),
            "candidate_process_fingerprint": "8" * 64,
            "_argv": (
                str(self.resolved_executable),
                EXPECTED_UNRESTRICTED_FLAG,
            ),
            "_launch_identity": {
                "repo": str(self.workspace),
                "argv_sha256": "9" * 64,
                "env_names": ["CODEX_HOME"],
                "environment_sha256": "a" * 64,
            },
        }
        values.update(overrides)
        return CodexLaunchContext(**values)

    def _plan(
        self,
        *,
        context=None,
        manifest=None,
        contract=None,
        expected_contract_identity=None,
        expected_run_identity=None,
    ):
        selected = self.context if context is None else context
        with mock.patch.object(
            workspace_module,
            "build_codex_launch_context",
            return_value=selected,
        ) as builder:
            plan = plan_codex_workspace_plane(
                manifest_path=self.base / "doctor.json",
                lane_root=self.lane,
                workspace_root=self.workspace,
                codex_home=self.codex_home,
                instruction_manifest=(
                    self.compiled.manifest if manifest is None else manifest
                ),
                effective_contract=(
                    self.compiled.rendered if contract is None else contract
                ),
                expected_contract_identity=(
                    self.expected_contract_identity
                    if expected_contract_identity is None
                    else expected_contract_identity
                ),
                expected_run_identity=(
                    self.expected_run_identity
                    if expected_run_identity is None
                    else expected_run_identity
                ),
            )
        builder.assert_called_once_with(
            manifest_path=self.base / "doctor.json",
            lane_root=self.lane,
            workspace_root=self.workspace,
            codex_home=self.codex_home,
        )
        return plan

    def test_plan_is_deterministic_body_free_and_disabled(self):
        first = self._plan()
        second = self._plan()
        self.assertEqual(first.to_dict(), second.to_dict())
        raw = first.to_dict()
        encoded = canonical_json_bytes(raw)
        self.assertNotIn(b"PUPPET_INSTRUCTION_BODY_CANARY", encoded)
        self.assertNotIn(self.compiled.rendered, encoded)
        self.assertEqual(
            raw["status"], {"surface": "hypothesis", "activation": "disabled"}
        )
        self.assertFalse(raw["launch_authorized"])
        self.assertFalse(raw["materialization_supported"])
        self.assertFalse(raw["rollback_supported"])
        self.assertFalse(raw["recovery_supported"])
        workspace = str(self.workspace.resolve())
        codex_home = str(self.codex_home.resolve())
        self.assertEqual(raw["launch_delta"], {"argv": ["-C", workspace]})
        admitted = raw["admitted_launch_plan"]
        self.assertEqual(
            admitted["argv"],
            [
                str(self.resolved_executable),
                EXPECTED_UNRESTRICTED_FLAG,
                "-C",
                workspace,
            ],
        )
        self.assertEqual(admitted["session"], self.expected_run_identity["session"])
        self.assertEqual(admitted["run_id"], self.expected_run_identity["run_id"])
        self.assertEqual(admitted["cwd"], workspace)
        self.assertEqual(admitted["env_names"], ["CODEX_HOME"])
        self.assertEqual(
            admitted["env_fingerprint"],
            sha256_bytes(
                canonical_json_bytes([["CODEX_HOME", codex_home]])
            ),
        )
        self.assertEqual(raw["planned_artifact"]["relative_path"], "AGENTS.md")
        self.assertEqual(
            raw["planned_artifact"]["content_sha256"],
            sha256_bytes(self.compiled.rendered),
        )
        self.assertEqual(
            first.planned_artifact_path, self.workspace.resolve() / "AGENTS.md"
        )
        self.assertEqual(repr(first).find("PUPPET_INSTRUCTION_BODY_CANARY"), -1)

    def test_admitted_plan_ignores_ambient_values_and_has_no_selectors_or_body(self):
        with mock.patch.dict(
            os.environ,
            {
                "CODEX_ACCESS_TOKEN": "ambient-token-canary",
                "HOME": "/ambient/home-canary",
                "PATH": "/ambient/path-canary",
            },
        ):
            admitted = self._plan().to_dict()["admitted_launch_plan"]
        encoded = canonical_json_bytes(admitted)
        self.assertEqual(admitted["env_names"], ["CODEX_HOME"])
        for forbidden in (
            b"ambient-token-canary",
            b"ambient/home-canary",
            b"ambient/path-canary",
            b"PUPPET_INSTRUCTION_BODY_CANARY",
            b"--model",
            b"--profile",
            b"--config",
            b"--effort",
        ):
            self.assertNotIn(forbidden, encoded)

    def test_public_api_has_no_task_body_or_authority_inputs(self):
        parameters = inspect.signature(plan_codex_workspace_plane).parameters
        self.assertEqual(
            set(parameters),
            {
                "manifest_path",
                "lane_root",
                "workspace_root",
                "codex_home",
                "instruction_manifest",
                "effective_contract",
                "expected_contract_identity",
                "expected_run_identity",
            },
        )
        for forbidden in (
            "task",
            "addendum",
            "token",
            "launch_authorized",
            "receipt",
            "journal",
        ):
            self.assertNotIn(forbidden, parameters)

    def test_existing_or_symlinked_agents_file_is_rejected(self):
        candidates = ("regular", "symlink")
        for kind in candidates:
            with self.subTest(kind=kind):
                candidate = self.workspace / "AGENTS.md"
                if kind == "regular":
                    candidate.write_text("existing", encoding="utf-8")
                else:
                    target = self.base / "outside-agents"
                    target.write_text("outside", encoding="utf-8")
                    candidate.symlink_to(target)
                try:
                    with self.assertRaisesRegex(ConflictError, "must be absent"):
                        self._plan()
                finally:
                    candidate.unlink()

    def test_contract_body_and_manifest_drift_are_rejected(self):
        with self.assertRaisesRegex(IdentityError, "bytes changed"):
            self._plan(contract=self.compiled.rendered + b"x")
        manifest = copy.deepcopy(self.compiled.manifest)
        manifest["rendered_sha256"] = "b" * 64
        with self.assertRaises(ValidationError):
            self._plan(manifest=manifest)

    def test_semantically_valid_cross_contract_workspace_and_run_are_rejected(self):
        cases = (
            {
                "contract_identity": {
                    "fingerprint": "3" * 64,
                    "controller": "controller-a",
                    "target": "claude",
                    "task_profile": QUALIFICATION_PROFILE,
                }
            },
            {
                "contract_identity": {
                    "fingerprint": "c" * 64,
                    "controller": "controller-b",
                    "target": "codex",
                    "task_profile": QUALIFICATION_PROFILE,
                }
            },
            {
                "workspace_identity": {
                    "fixture_fingerprint": "4" * 64,
                    "workspace": "isolated_conformance_fixture",
                }
            },
            {
                "run_identity": {
                    "session": "alternate-session",
                    "run_id": "alternate-run",
                    "nonce": "cross-run-nonce",
                }
            },
        )
        baseline = {
            "contract_identity": {
                "fingerprint": "3" * 64,
                "controller": "controller-a",
                "target": "codex",
                "task_profile": QUALIFICATION_PROFILE,
            },
            "workspace_identity": {
                "fixture_fingerprint": tree_fingerprint(self.workspace),
                "workspace": "isolated_conformance_fixture",
            },
            "run_identity": {
                "session": "codex-session-a",
                "run_id": "codex-run-a",
                "nonce": "codex-nonce-a",
            },
        }
        for mutation in cases:
            with self.subTest(mutation=mutation):
                identities = copy.deepcopy(baseline)
                identities.update(mutation)
                compiled = compile_instruction_wrapper(
                    target="codex",
                    task="cross-identity canary",
                    contract_identity=identities["contract_identity"],
                    workspace_identity=identities["workspace_identity"],
                    run_identity=identities["run_identity"],
                    model_binding="default",
                    effort_binding="default",
                )
                with self.assertRaises(IdentityError):
                    self._plan(
                        manifest=compiled.manifest,
                        contract=compiled.rendered,
                    )

    def test_context_tuple_and_authority_tampering_are_rejected(self):
        mutations = (
            {"target": "claude"},
            {"launch_authorized": True},
            {"model_selection": "alternate"},
            {"auth_route": "caller_supplied"},
            {"blockers": ()},
            {"_argv": (str(self.resolved_executable), "--model", "other")},
        )
        for values in mutations:
            with self.subTest(values=values):
                with self.assertRaises((IdentityError, ValidationError)):
                    self._plan(context=self._context(**values))

    def test_self_consistent_plan_tampering_is_rejected(self):
        raw = self._plan().to_dict()
        mutations = (
            ("status", {"surface": "factual", "activation": "qualified"}),
            ("launch_authorized", True),
            ("launch_delta", {"argv": ["-C", str(self.base)]}),
            ("requested_executable_path", str(self.base / "other-codex")),
            (
                "admitted_launch_plan",
                {
                    **raw["admitted_launch_plan"],
                    "argv": [
                        str(self.resolved_executable),
                        EXPECTED_UNRESTRICTED_FLAG,
                        "--model",
                        "alternate",
                        "-C",
                        str(self.workspace.resolve()),
                    ],
                },
            ),
        )
        for name, value in mutations:
            with self.subTest(name=name):
                changed = copy.deepcopy(raw)
                changed[name] = value
                changed["plan_sha256"] = sha256_bytes(
                    canonical_json_bytes(
                        {
                            key: item
                            for key, item in changed.items()
                            if key != "plan_sha256"
                        }
                    )
                )
                with self.assertRaises((IdentityError, UnsupportedError)):
                    CodexWorkspacePlan.from_dict(changed)

    def test_root_replacement_and_context_drift_fail_revalidation(self):
        plan = self._plan()
        original = self.workspace
        moved = self.lane / "workspace-old"
        original.rename(moved)
        original.mkdir(mode=0o700)
        original.chmod(0o700)
        with self.assertRaises(IdentityError):
            self._plan()

        moved.rmdir()
        changed = self._context(candidate_process_fingerprint="f" * 64)
        with mock.patch.object(
            workspace_module, "build_codex_launch_context", return_value=changed
        ):
            with self.assertRaises(IdentityError):
                revalidate_codex_workspace_plan(
                    plan,
                    manifest_path=self.base / "doctor.json",
                    lane_root=self.lane,
                    workspace_root=self.workspace,
                    codex_home=self.codex_home,
                    instruction_manifest=self.compiled.manifest,
                    effective_contract=self.compiled.rendered,
                    expected_contract_identity=self.expected_contract_identity,
                    expected_run_identity=self.expected_run_identity,
                )

    def test_lifecycle_entrypoints_are_unconditionally_disabled(self):
        plan = self._plan()
        target = self.workspace / "AGENTS.md"
        for operation in (
            lambda: materialize_codex_workspace_plane(
                plan, effective_contract=self.compiled.rendered
            ),
            lambda: verify_codex_workspace_plane(plan, receipt={"result": "ok"}),
            lambda: rollback_codex_workspace_plane(
                plan, exact_halt_proof={"claimed": True}
            ),
            lambda: recover_codex_workspace_plane(
                plan, rollback_record={"claimed": True}
            ),
        ):
            with self.subTest(operation=operation):
                with self.assertRaisesRegex(UnsupportedError, "remain disabled"):
                    operation()
                self.assertFalse(target.exists())

    def test_plan_rejects_non_context_and_detaches_public_copies(self):
        with self.assertRaisesRegex(ValidationError, "launch context is invalid"):
            self._plan(context=object())
        plan = self._plan()
        detached = plan.to_dict()
        detached["planned_artifact"]["relative_path"] = "changed"
        self.assertEqual(
            plan.to_dict()["planned_artifact"]["relative_path"], "AGENTS.md"
        )

    def test_module_has_no_mutating_or_process_surface(self):
        source = inspect.getsource(workspace_module)
        for forbidden in (
            "subprocess.",
            ".write_text(",
            ".write_bytes(",
            ".unlink(",
            ".mkdir(",
            "os.remove(",
            "os.rename(",
            "os.kill(",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
