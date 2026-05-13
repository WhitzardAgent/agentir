"""Slice training pass -- creates trainable projections from canonical IR.

This pass filters events to produce a training-ready IR:
- Drops non-trainable events (visibility.trainable=False) unless the backend
  explicitly requests them via PassContext.options.
- Preserves tool_call / tool_result adjacency so that paired events are never
  split apart (dropping one forces the other to be dropped as well).
- Merges adjacent user/assistant message events when safe by filtering out
  intermediate non-trainable noise while keeping them as separate events.
- Preserves provenance and metadata needed for attribution.
- Sets the IR level to TRAINING.
"""

from __future__ import annotations

from typing import Any

from agentir.diagnostics.diagnostic import Diagnostic
from agentir.ir.base import DiagnosticSeverity, EventType, IRLevel, PassKind
from agentir.ir.episode import Episode
from agentir.ir.event import Event
from agentir.ir.record import AgentIRRecord
from agentir.passes.base import AgentIRPass, PassContext, PassResult
from agentir.passes.registry import register_pass

# Event types that form a bonded pair -- dropping one requires dropping the
# other to keep the training slice consistent.
_TOOL_CALL_TYPES: set[EventType] = {
    EventType.TOOL_CALL,
    EventType.TERMINAL_COMMAND,
    EventType.FILE_READ,
    EventType.FILE_WRITE,
    EventType.FILE_PATCH,
    EventType.BROWSER_ACTION,
    EventType.MEMORY_READ,
    EventType.MEMORY_WRITE,
    EventType.AGENT_HANDOFF,
    EventType.SUBTASK_SPAWN,
}

_TOOL_RESULT_TYPES: set[EventType] = {
    EventType.TOOL_RESULT,
    EventType.TERMINAL_OUTPUT,
    EventType.BROWSER_OBSERVATION,
    EventType.SUBTASK_RESULT,
    EventType.TOOL_MESSAGE,
}

# Message events that are candidates for adjacent-merge filtering.
_MESSAGE_TYPES: set[EventType] = {
    EventType.USER_MESSAGE,
    EventType.ASSISTANT_MESSAGE,
}


class SliceTrainingPass(AgentIRPass):
    """Transform pass that slices a canonical record into a training-ready form."""

    name: str = "slice-training"
    kind: PassKind = PassKind.TRANSFORM

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, record: AgentIRRecord, ctx: PassContext) -> PassResult:
        diagnostics: list[Diagnostic] = []
        metrics: dict[str, Any] = {}

        keep_non_trainable: bool = ctx.options.get("keep_non_trainable", False)

        total_events_before = sum(len(ep.events) for ep in record.episodes)
        filtered_episodes: list[Episode] = []

        for episode in record.episodes:
            filtered_events = self._filter_events(
                episode.events,
                keep_non_trainable=keep_non_trainable,
                diagnostics=diagnostics,
            )
            filtered_episodes.append(
                Episode(
                    episode_id=episode.episode_id,
                    task_id=episode.task_id,
                    attempt_id=episode.attempt_id,
                    parent_episode_id=episode.parent_episode_id,
                    segments=episode.segments,
                    events=filtered_events,
                    state_timeline=episode.state_timeline,
                    outcome=episode.outcome,
                    metadata=episode.metadata,
                )
            )

        total_events_after = sum(len(ep.events) for ep in filtered_episodes)
        metrics["events_before"] = total_events_before
        metrics["events_after"] = total_events_after
        metrics["events_dropped"] = total_events_before - total_events_after

        updated_record = AgentIRRecord(
            ir_version=record.ir_version,
            record_id=record.record_id,
            level=IRLevel.TRAINING,
            source=record.source,
            task=record.task,
            tool_registry=record.tool_registry,
            actors=record.actors,
            episodes=filtered_episodes,
            artifacts=record.artifacts,
            outcome=record.outcome,
            diagnostics=record.diagnostics,
            raw=record.raw,
            metadata=record.metadata,
        )

        return PassResult(
            record=updated_record,
            diagnostics=diagnostics,
            metrics=metrics,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _filter_events(
        events: list[Event],
        *,
        keep_non_trainable: bool,
        diagnostics: list[Diagnostic],
    ) -> list[Event]:
        """Filter events according to training-slice rules.

        Rules applied in order:
        1. Drop events where ``visibility.trainable`` is False, unless
           *keep_non_trainable* is True (backend opt-in).
        2. Preserve tool_call / tool_result adjacency: if one side of a bonded
           pair is dropped, the partner is dropped as well.
        3. Adjacent user/assistant message events are kept as separate events
           but intermediate non-trainable events between them are filtered out
           so the messages remain adjacent in the output.
        4. Provenance and metadata are always preserved on surviving events for
           attribution.
        """
        # Phase 1: initial trainable filter
        trainable_mask: list[bool] = []
        for event in events:
            if keep_non_trainable:
                trainable_mask.append(True)
            else:
                trainable_mask.append(event.visibility.trainable)

        # Phase 2: enforce tool_call / tool_result adjacency.
        # Every tool-call event tracks its result(s) via child_event_ids and
        # every tool-result references its call via parent_event_ids.  We build
        # a lookup so that dropping one side of the pair forces the other out.
        id_to_idx: dict[str, int] = {event.event_id: i for i, event in enumerate(events)}

        for i, event in enumerate(events):
            if not trainable_mask[i]:
                continue
            if event.event_type in _TOOL_CALL_TYPES:
                # If all children (results) are dropped, drop the call too.
                if event.child_event_ids:
                    any_child_alive = any(
                        id_to_idx.get(cid, -1) != -1 and trainable_mask[id_to_idx[cid]]
                        for cid in event.child_event_ids
                    )
                    if not any_child_alive:
                        trainable_mask[i] = False
                        diagnostics.append(
                            Diagnostic(
                                code="slice-training:dropped-orphan-call",
                                severity=DiagnosticSeverity.INFO,
                                message=(
                                    f"Dropping tool call event "
                                    f"{event.event_id!r} because all its "
                                    f"result events were dropped."
                                ),
                                event_id=event.event_id,
                            )
                        )
            elif event.event_type in _TOOL_RESULT_TYPES:
                # If the parent call was dropped, drop the result too.
                if event.parent_event_ids:
                    any_parent_alive = any(
                        id_to_idx.get(pid, -1) != -1 and trainable_mask[id_to_idx[pid]]
                        for pid in event.parent_event_ids
                    )
                    if not any_parent_alive:
                        trainable_mask[i] = False
                        diagnostics.append(
                            Diagnostic(
                                code="slice-training:dropped-orphan-result",
                                severity=DiagnosticSeverity.INFO,
                                message=(
                                    f"Dropping tool result event "
                                    f"{event.event_id!r} because its "
                                    f"call event was dropped."
                                ),
                                event_id=event.event_id,
                            )
                        )

        # Phase 3: build the filtered list, preserving provenance.
        filtered: list[Event] = []
        for i, event in enumerate(events):
            if trainable_mask[i]:
                # Ensure provenance is preserved for attribution even if it
                # was partially stripped in earlier passes.
                filtered.append(
                    Event(
                        event_id=event.event_id,
                        idx=len(filtered),
                        event_type=event.event_type,
                        actor_id=event.actor_id,
                        role=event.role,
                        parent_event_ids=event.parent_event_ids,
                        child_event_ids=event.child_event_ids,
                        segment_id=event.segment_id,
                        timestamp=event.timestamp,
                        content=event.content,
                        action=event.action,
                        observation=event.observation,
                        state_delta=event.state_delta,
                        control=event.control,
                        artifacts=event.artifacts,
                        provenance=event.provenance,
                        visibility=event.visibility,
                        raw=event.raw,
                        metadata=event.metadata,
                    )
                )

        return filtered


register_pass(SliceTrainingPass())
