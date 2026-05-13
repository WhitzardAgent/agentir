"""Event model for individual trajectory steps."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from agentir.ir.action import Action
from agentir.ir.base import EventType, MessageRole
from agentir.ir.content import ContentBlock
from agentir.ir.control import ControlInfo
from agentir.ir.observation import Observation
from agentir.ir.provenance import Provenance
from agentir.ir.state import StateDelta
from agentir.ir.visibility import Visibility


class Event(BaseModel):
    """A single event in a trajectory."""

    model_config = ConfigDict(extra="allow")

    event_id: str
    idx: int
    event_type: EventType
    actor_id: str | None = None
    role: MessageRole | None = None
    parent_event_ids: list[str] = Field(default_factory=list)
    child_event_ids: list[str] = Field(default_factory=list)
    segment_id: str | None = None
    timestamp: str | None = None
    content: list[ContentBlock] = Field(default_factory=list)
    action: Action | None = None
    observation: Observation | None = None
    state_delta: StateDelta | None = None
    control: ControlInfo | None = None
    artifacts: list[str] = Field(default_factory=list)
    provenance: Provenance | None = None
    visibility: Visibility = Field(default_factory=Visibility)
    raw: dict = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)
