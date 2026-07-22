"""Portable target-adapter policy with no prompt content in argv."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .adapter_manifest import AdapterManifest
from .errors import UnsupportedError, ValidationError


@dataclass(frozen=True)
class AdapterSpec:
    name: str
    required_prefix: Optional[str] = None
    graceful_halt_actions: Tuple[str, ...] = ("exact_pid_sigint",)

    def envelope(self, message: str) -> str:
        if not isinstance(message, str) or not message.strip():
            raise ValidationError("message must not be empty")
        body = message.strip()
        lowered = body.lower()
        if self.name == "agy":
            if lowered.startswith("/btw") or lowered.startswith("/side"):
                raise ValidationError("AGY side-channel commands are forbidden")
            if lowered.startswith("/teamwork-preview"):
                raise ValidationError("caller must not provide the AGY native prefix")
            return "/teamwork-preview " + body
        return body

    def build_launch_argv(
        self,
        manifest: AdapterManifest,
        requested_model: Optional[str] = None,
        requested_effort: Optional[str] = None,
    ) -> List[str]:
        manifest.require("launch")
        mapping = manifest.raw["yolo_mapping"]
        if not mapping.get("complete"):
            raise UnsupportedError("exact YOLO and sandbox-off mapping is incomplete")
        argv = mapping.get("launch_argv")
        if not isinstance(argv, list) or not argv or not all(isinstance(item, str) for item in argv):
            raise ValidationError("manifest launch_argv is invalid")
        if argv[0] != manifest.raw["executable"]["resolved_path"]:
            raise ValidationError("launch executable is not the fingerprinted executable")
        argv = list(argv)
        if any("\x00" in item or "\n" in item or "\r" in item for item in argv):
            raise ValidationError("manifest launch arguments contain control characters")
        if requested_model is not None:
            if (
                not isinstance(requested_model, str)
                or not requested_model
                or len(requested_model) > 200
                or any(char in requested_model for char in "\x00\n\r")
            ):
                raise ValidationError("requested model is invalid")
            model_flag = mapping.get("model_flag")
            if not isinstance(model_flag, str):
                raise UnsupportedError("requested model selection is not proved")
            argv.extend([model_flag, requested_model])
        if requested_effort is not None:
            if (
                not isinstance(requested_effort, str)
                or not requested_effort
                or len(requested_effort) > 80
                or any(char in requested_effort for char in "\x00\n\r")
            ):
                raise ValidationError("requested effort is invalid")
            effort_flag = mapping.get("effort_flag")
            if not isinstance(effort_flag, str):
                raise UnsupportedError("requested effort selection is not proved")
            argv.extend([effort_flag, requested_effort])
        return argv


ADAPTERS: Dict[str, AdapterSpec] = {
    name: AdapterSpec(
        name=name,
        required_prefix="/teamwork-preview" if name == "agy" else None,
        graceful_halt_actions=(
            ("tmux_pane_eof", "tmux_pane_eof")
            if name == "agy"
            else ("exact_pid_sigint",)
        ),
    )
    for name in ("agy", "cursor", "claude", "codex", "grok")
}


def adapter_for(target: str) -> AdapterSpec:
    try:
        return ADAPTERS[target]
    except KeyError as exc:
        raise ValidationError("unsupported adapter target") from exc
