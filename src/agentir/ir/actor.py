"""Actor specification model."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from agentir.ir.base import ActorKind


class ActorSpec(BaseModel):
    """Specification of an actor in the trajectory."""

    actor_id: str
    kind: ActorKind
    name: str | None = None
    model: str | None = None
    role: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
