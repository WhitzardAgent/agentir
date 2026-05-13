"""Backend protocol and context models."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from agentir.backends.loss import LoweringResult
from agentir.ir.record import AgentIRRecord


class BackendContext(BaseModel):
    """Context passed to backends controlling lowering behaviour."""

    reasoning_policy: str | None = None
    include_reasoning: bool = False
    tool_policy: str = "structured"  # structured | inline | drop
    options: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class Backend(Protocol):
    """Protocol that every lowering backend must implement."""

    name: str

    def lower_record(self, record: AgentIRRecord, ctx: BackendContext) -> LoweringResult: ...
