"""Pass that pairs TOOL_CALL events with their corresponding TOOL_RESULT events."""

from __future__ import annotations

from agentir.diagnostics.codes import DiagnosticCodes, make_diagnostic
from agentir.diagnostics.diagnostic import Diagnostic
from agentir.ir.base import EventType, PassKind
from agentir.ir.episode import Episode
from agentir.ir.event import Event
from agentir.ir.provenance import Provenance
from agentir.ir.record import AgentIRRecord
from agentir.passes.base import AgentIRPass, PassContext, PassResult
from agentir.passes.registry import register_pass


def _tool_call_id(event: Event) -> str | None:
    """Extract tool_call_id from a TOOL_CALL event's action field."""
    if event.action is not None:
        return event.action.tool_call_id
    return None


def _tool_result_call_id(event: Event) -> str | None:
    """Extract tool_call_id that a TOOL_RESULT event refers to.

    Checks, in order:
    1. observation.metadata["tool_call_id"]
    2. metadata["tool_call_id"]
    3. raw["tool_call_id"]
    """
    if event.observation is not None and event.observation.metadata.get("tool_call_id"):
        return event.observation.metadata["tool_call_id"]
    if event.metadata.get("tool_call_id"):
        return event.metadata["tool_call_id"]
    if event.raw.get("tool_call_id"):
        return event.raw["tool_call_id"]
    return None


def _framework_specific_call_id(tool_call: Event, tool_result: Event) -> str | None:
    """Try to match via source-framework-specific fields.

    Checks common framework conventions:
    - OpenAI-style: action.tool_call_id on the call, metadata["tool_call_id"] on result
    - Anthropic-style: action.tool_use_id / metadata["tool_use_id"]
    - Generic: matching tool_name between call and result
    """
    # Check tool_use_id (Anthropic-style)
    if tool_call.action and tool_call.action.metadata.get("tool_use_id"):
        call_id = tool_call.action.metadata["tool_use_id"]
        for candidate in (tool_result.observation, tool_result):
            meta = candidate.metadata if candidate else {}
            if meta.get("tool_use_id") == call_id:
                return call_id

    # Check function name matching as last resort
    if tool_call.action and tool_call.action.tool_name:
        tool_name = tool_call.action.tool_name
        result_name = (
            tool_result.metadata.get("tool_name")
            or (
                tool_result.observation.metadata.get("tool_name")
                if tool_result.observation
                else None
            )
            or tool_result.raw.get("tool_name")
        )
        if result_name and result_name == tool_name:
            return result_name

    return None


def _pair_by_call_id(
    tool_calls: list[Event],
    tool_results: list[Event],
) -> list[tuple[Event, Event, str | None]]:
    """Pair tool calls and results by exact tool_call_id match.

    Returns list of (tool_call, tool_result, matched_id) tuples.
    """
    matched: list[tuple[Event, Event, str | None]] = []
    matched_call_ids: set[str] = set()
    matched_result_ids: set[str] = set()

    # Build lookup from tool_call_id -> tool_result event
    result_by_id: dict[str, Event] = {}
    for result in tool_results:
        rid = _tool_result_call_id(result)
        if rid:
            result_by_id[rid] = result

    # Match calls to results by their action.tool_call_id
    for call in tool_calls:
        cid = _tool_call_id(call)
        if cid and cid in result_by_id:
            result = result_by_id[cid]
            matched.append((call, result, cid))
            matched_call_ids.add(call.event_id)
            matched_result_ids.add(result.event_id)

    remaining_calls = [c for c in tool_calls if c.event_id not in matched_call_ids]
    remaining_results = [r for r in tool_results if r.event_id not in matched_result_ids]

    return matched, remaining_calls, remaining_results


def _pair_by_adjacency(
    all_events: list[Event],
    remaining_calls: list[Event],
    remaining_results: list[Event],
) -> list[tuple[Event, Event, str | None]]:
    """Pair unmatched tool calls with the next TOOL_RESULT event after them."""
    remaining_call_ids = {c.event_id for c in remaining_calls}
    remaining_result_ids = {r.event_id for r in remaining_results}

    # Build event index for fast lookup
    event_idx_map: dict[str, int] = {}
    for i, ev in enumerate(all_events):
        event_idx_map[ev.event_id] = i

    matched: list[tuple[Event, Event, str | None]] = []
    newly_matched_calls: set[str] = set()
    newly_matched_results: set[str] = set()

    for call in remaining_calls:
        call_idx = event_idx_map.get(call.event_id)
        if call_idx is None:
            continue
        # Scan forward for the next unmatched TOOL_RESULT
        for j in range(call_idx + 1, len(all_events)):
            candidate = all_events[j]
            if (
                candidate.event_type == EventType.TOOL_RESULT
                and candidate.event_id in remaining_result_ids
            ):
                # Skip results that carry an explicit tool_call_id pointing elsewhere
                result_cid = _tool_result_call_id(candidate)
                call_cid = _tool_call_id(call)
                if result_cid is not None and result_cid != call_cid:
                    continue
                matched.append((call, candidate, None))
                newly_matched_calls.add(call.event_id)
                newly_matched_results.add(candidate.event_id)
                break
            # Stop scanning if we hit another TOOL_CALL before finding a result
            if candidate.event_type == EventType.TOOL_CALL:
                break

    still_remaining_calls = [c for c in remaining_calls if c.event_id not in newly_matched_calls]
    still_remaining_results = [
        r for r in remaining_results if r.event_id not in newly_matched_results
    ]

    return matched, still_remaining_calls, still_remaining_results


def _pair_by_framework_fields(
    remaining_calls: list[Event],
    remaining_results: list[Event],
) -> list[tuple[Event, Event, str | None]]:
    """Pair remaining calls and results using framework-specific conventions."""
    matched: list[tuple[Event, Event, str | None]] = []
    matched_result_ids: set[str] = set()

    for call in remaining_calls:
        for result in remaining_results:
            if result.event_id in matched_result_ids:
                continue
            fw_id = _framework_specific_call_id(call, result)
            if fw_id is not None:
                matched.append((call, result, fw_id))
                matched_result_ids.add(result.event_id)
                break

    still_remaining_calls = [
        c for c in remaining_calls if c.event_id not in {m[0].event_id for m in matched}
    ]
    still_remaining_results = [r for r in remaining_results if r.event_id not in matched_result_ids]

    return matched, still_remaining_calls, still_remaining_results


class PairToolResultsPass(AgentIRPass):
    """Pair TOOL_CALL events with their corresponding TOOL_RESULT events.

    Matching priority:
    1. Exact tool_call_id match
    2. Adjacent tool result after tool call
    3. Source framework-specific fields
    """

    name = "pair-tool-results"
    kind = PassKind.CANONICALIZE

    def run(self, record: AgentIRRecord, ctx: PassContext) -> PassResult:
        diagnostics: list[Diagnostic] = []
        all_matched: list[tuple[Event, Event, str | None]] = []

        updated_episodes: list[Episode] = []

        for episode in record.episodes:
            all_events = list(episode.events)

            # Separate tool calls and tool results
            tool_calls = [e for e in all_events if e.event_type == EventType.TOOL_CALL]
            tool_results = [e for e in all_events if e.event_type == EventType.TOOL_RESULT]

            # Phase 1: Exact tool_call_id match
            matched_1, rem_calls, rem_results = _pair_by_call_id(tool_calls, tool_results)
            all_matched.extend(matched_1)

            # Phase 2: Adjacent pairing
            matched_2, rem_calls, rem_results = _pair_by_adjacency(
                all_events,
                rem_calls,
                rem_results,
            )
            all_matched.extend(matched_2)

            # Phase 3: Framework-specific fields
            matched_3, rem_calls, rem_results = _pair_by_framework_fields(
                rem_calls,
                rem_results,
            )
            all_matched.extend(matched_3)

            # Emit PAIR001 for unmatched tool calls
            for unmatched_call in rem_calls:
                diagnostics.append(
                    make_diagnostic(
                        DiagnosticCodes.PAIR001,
                        event_id=unmatched_call.event_id,
                        suggestion="Check if the tool result was dropped during conversion",
                    )
                )

            # Emit PAIR002 for unmatched tool results
            for unmatched_result in rem_results:
                diagnostics.append(
                    make_diagnostic(
                        DiagnosticCodes.PAIR002,
                        event_id=unmatched_result.event_id,
                        suggestion="Check if the tool call was dropped during conversion",
                    )
                )

            # Apply parent/child links to matched pairs
            event_map: dict[str, Event] = {e.event_id: e.model_copy(deep=True) for e in all_events}

            for call, result, matched_id in all_matched:
                call_copy = event_map[call.event_id]
                result_copy = event_map[result.event_id]

                # Set child_event_ids on the tool_call
                if result_copy.event_id not in call_copy.child_event_ids:
                    call_copy.child_event_ids = list(call_copy.child_event_ids) + [
                        result_copy.event_id
                    ]

                # Set parent_event_ids on the tool_result
                if call_copy.event_id not in result_copy.parent_event_ids:
                    result_copy.parent_event_ids = list(result_copy.parent_event_ids) + [
                        call_copy.event_id
                    ]

                # If paired by adjacent or framework match (not exact ID),
                # and the call lacks a tool_call_id, set one with reduced confidence
                if matched_id is None and _tool_call_id(call_copy) is None:
                    synthetic_id = f"synth_{call_copy.event_id}"
                    if call_copy.action is not None:
                        call_copy.action = call_copy.action.model_copy(
                            update={
                                "tool_call_id": synthetic_id,
                            }
                        )
                    else:
                        from agentir.ir.action import Action
                        from agentir.ir.base import ActionKind, CallStyle, SideEffectLevel

                        call_copy.action = Action(
                            kind=ActionKind.GENERIC_TOOL,
                            tool_call_id=synthetic_id,
                            call_style=CallStyle.INFERRED,
                            side_effect_level=SideEffectLevel.UNKNOWN,
                        )
                    # Mark provenance confidence < 1.0 since we invented an ID
                    if call_copy.provenance is not None:
                        call_copy.provenance = call_copy.provenance.model_copy(
                            update={
                                "confidence": min(call_copy.provenance.confidence, 0.7),
                            }
                        )
                    else:
                        call_copy.provenance = Provenance(
                            confidence=0.7,
                            parser=self.name,
                        )

                # Propagate tool_call_id to the result if the call has one
                # and the result does not already reference it
                if call_copy.action and call_copy.action.tool_call_id:
                    tcid = call_copy.action.tool_call_id
                    if _tool_result_call_id(result_copy) is None:
                        if result_copy.observation is not None:
                            result_copy.observation = result_copy.observation.model_copy(
                                update={
                                    "metadata": {
                                        **result_copy.observation.metadata,
                                        "tool_call_id": tcid,
                                    },
                                }
                            )
                        else:
                            result_copy = result_copy.model_copy(
                                update={
                                    "metadata": {**result_copy.metadata, "tool_call_id": tcid},
                                }
                            )

                event_map[call.event_id] = call_copy
                event_map[result.event_id] = result_copy

            # Rebuild events list preserving original order
            updated_events = [event_map.get(e.event_id, e) for e in all_events]

            updated_episodes.append(
                Episode(
                    episode_id=episode.episode_id,
                    task_id=episode.task_id,
                    attempt_id=episode.attempt_id,
                    parent_episode_id=episode.parent_episode_id,
                    segments=episode.segments,
                    events=updated_events,
                    state_timeline=episode.state_timeline,
                    outcome=episode.outcome,
                    metadata=episode.metadata,
                )
            )

        updated = record.model_copy(update={"episodes": updated_episodes})
        return PassResult(record=updated, diagnostics=diagnostics)


register_pass(PairToolResultsPass())
