"""Episode, segment, and trajectory models."""

from __future__ import annotations

from pydantic import BaseModel, Field

from agentir.ir.base import SegmentKind
from agentir.ir.event import Event
from agentir.ir.outcome import Outcome
from agentir.ir.state import StateSnapshot


class Segment(BaseModel):
    """A segment of a trajectory grouping related events."""

    segment_id: str
    kind: SegmentKind
    name: str | None = None
    event_ids: list[str] = Field(default_factory=list)
    parent_segment_id: str | None = None
    metadata: dict = Field(default_factory=dict)


class Episode(BaseModel):
    """An episode comprising a complete task attempt."""

    episode_id: str
    task_id: str | None = None
    attempt_id: str | None = None
    parent_episode_id: str | None = None
    segments: list[Segment] = Field(default_factory=list)
    events: list[Event] = Field(default_factory=list)
    state_timeline: list[StateSnapshot] = Field(default_factory=list)
    outcome: Outcome | None = None
    metadata: dict = Field(default_factory=dict)
