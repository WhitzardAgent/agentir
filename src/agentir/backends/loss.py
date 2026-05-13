"""Loss reporting models for backend lowering."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from agentir.ir.base import DiagnosticSeverity, LoweringStatus


class LossItem(BaseModel):
    """A single loss incurred during lowering."""

    severity: DiagnosticSeverity
    code: str
    field: str | None = None
    message: str
    event_id: str | None = None
    suggestion: str | None = None


class LossReport(BaseModel):
    """Aggregated loss report for a single record lowering."""

    target: str
    status: LoweringStatus
    losses: list[LossItem] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)


class LoweringResult(BaseModel):
    """Result of lowering a single AgentIRRecord to a target format."""

    output: Any
    report: LossReport
