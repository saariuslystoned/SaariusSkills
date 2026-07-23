from __future__ import annotations

from typing import Any


class HerdrPuppetError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        exit_code: int = 2,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}
        self.exit_code = exit_code

    def as_json(self) -> dict[str, Any]:
        return {
            "schema": "herdr-puppet.error.v1",
            "result": "blocked",
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            },
        }
