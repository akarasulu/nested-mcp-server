"""Error types and normalization helpers for MCP responses."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class MCPError(Exception):
    """Normalized error used across adapters and tools."""

    code: str
    message: str
    retryable: bool = False
    details: dict[str, Any] = field(default_factory=dict)

    def to_envelope(self) -> dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "retryable": self.retryable,
                "details": self.details,
            }
        }


def error_envelope(code: str, message: str, *, retryable: bool = False, **details: Any) -> dict[str, Any]:
    """Create a deterministic error envelope without raising."""
    return MCPError(code=code, message=message, retryable=retryable, details=details).to_envelope()
