from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from agentir.ir.base import DiagnosticSeverity
from agentir.ir.provenance import Provenance


class Diagnostic(BaseModel):
    code: str
    severity: DiagnosticSeverity
    message: str
    source: Provenance | None = None
    event_id: str | None = None
    field: str | None = None
    suggestion: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
