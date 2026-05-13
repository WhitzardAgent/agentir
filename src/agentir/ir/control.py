"""Control flow information model."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from agentir.ir.base import ControlFlow


class ControlInfo(BaseModel):
    """Control flow metadata for an event."""

    flow: ControlFlow = ControlFlow.SEQUENCE
    block_id: str | None = None
    next_event_ids: list[str] = Field(default_factory=list)
    branch_condition: str | None = None
    retry_of_event_id: str | None = None
    loop_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
