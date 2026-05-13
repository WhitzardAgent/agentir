"""Action model for tool invocations and agent actions."""

from __future__ import annotations

from pydantic import BaseModel, Field

from agentir.ir.base import ActionKind, CallStyle, SideEffectLevel


class Action(BaseModel):
    """An action performed by an actor."""

    kind: ActionKind
    tool_name: str | None = None
    tool_call_id: str | None = None
    arguments: dict = Field(default_factory=dict)
    normalized_arguments: dict = Field(default_factory=dict)
    call_style: CallStyle = CallStyle.UNKNOWN
    side_effect_level: SideEffectLevel = SideEffectLevel.UNKNOWN
    timeout_seconds: float | None = None
    metadata: dict = Field(default_factory=dict)
