"""Pass that extracts diffs into patch artifacts."""

from __future__ import annotations

import re

import unidiff

from agentir.diagnostics.codes import DiagnosticCodes, make_diagnostic
from agentir.diagnostics.diagnostic import Diagnostic
from agentir.ir.artifact import Artifact
from agentir.ir.base import ArtifactKind, EventType, PassKind
from agentir.ir.content import ContentBlock, ContentType
from agentir.ir.episode import Episode
from agentir.ir.event import Event
from agentir.ir.provenance import Provenance
from agentir.ir.record import AgentIRRecord
from agentir.ir.state import StateDelta
from agentir.passes.base import AgentIRPass, PassContext, PassResult
from agentir.passes.registry import register_pass

# Patterns for detecting unified diff blocks in assistant content
_DIFF_GIT_RE = re.compile(r"^diff --git", re.MULTILINE)
_DIFF_HEADER_RE = re.compile(r"^--- a/", re.MULTILINE)


def _extract_diff_blocks(text: str) -> list[str]:
    """Extract contiguous unified diff blocks from text.

    A diff block starts with a line matching ``diff --git`` or ``--- a/``
    and continues until the next blank line that is not inside a hunk or
    until end of text.
    """
    lines = text.split("\n")
    blocks: list[str] = []
    current: list[str] = []
    in_hunk = False

    for line in lines:
        is_diff_start = line.startswith("diff --git") or line.startswith("--- a/")
        is_hunk_line = (
            line.startswith("@@")
            or line.startswith("+")
            or line.startswith("-")
            or line.startswith(" ")
            or line.startswith("\\")
        )
        is_context_or_header = (
            line.startswith("index ") or line.startswith("--- ") or line.startswith("+++ ")
        )

        if is_diff_start and not in_hunk:
            # Start a new diff block
            if current:
                blocks.append("\n".join(current))
            current = [line]
            in_hunk = False
        elif current:
            # Inside a diff block
            if line.startswith("@@"):
                in_hunk = True
            elif in_hunk and line == "":
                # Blank line inside a hunk is part of context
                current.append(line)
            elif not in_hunk and line == "" and current:
                # Blank line outside hunk ends the block
                blocks.append("\n".join(current))
                current = []
                in_hunk = False
            else:
                current.append(line)
                # Stay in hunk if we see hunk lines
                if not line.startswith("@@") and (
                    line.startswith("+")
                    or line.startswith("-")
                    or line.startswith(" ")
                    or line.startswith("\\")
                ):
                    pass  # still in hunk or context
                elif (
                    not is_hunk_line
                    and not is_context_or_header
                    and not line.startswith("diff --git")
                ):
                    in_hunk = False
        elif not current and is_diff_start:
            current = [line]

    if current:
        blocks.append("\n".join(current))

    return blocks


def _parse_patch(diff_text: str) -> tuple[list[str], bool]:
    """Try to parse diff text with unidiff.

    Returns (changed_file_paths, parse_succeeded).
    """
    try:
        patch_set = unidiff.PatchSet(diff_text)
        paths = [pf.target_file for pf in patch_set if pf.target_file]
        return paths, True
    except Exception:
        return [], False


def _looks_like_diff(text: str) -> bool:
    """Heuristic check whether text resembles a diff even if unidiff failed."""
    return bool(_DIFF_GIT_RE.search(text) or _DIFF_HEADER_RE.search(text))


class ExtractPatchesPass(AgentIRPass):
    """Extract diffs from raw record fields and assistant content into patch artifacts."""

    name = "extract-patches"
    kind = PassKind.CANONICALIZE

    def run(self, record: AgentIRRecord, ctx: PassContext) -> PassResult:
        diagnostics: list[Diagnostic] = []
        artifacts: list[Artifact] = list(record.artifacts)
        events: list[Event] = []
        existing_ids: set[str] = set()

        for ep in record.episodes:
            events.extend(ep.events)
            existing_ids.update(e.event_id for e in ep.events)

        # Collect patch texts from various sources
        patch_sources: list[tuple[str, str, str | None]] = []  # (diff_text, source_field, event_id)

        raw_record = record.raw.get("record", {})
        top_level_raw = record.raw

        # Source 1: OpenHands model_patch
        model_patch = raw_record.get("model_patch")
        if model_patch and isinstance(model_patch, str) and model_patch.strip():
            patch_sources.append((model_patch.strip(), "record.model_patch", None))

        # Source 2: Claude Code gitdiff
        gitdiff = raw_record.get("gitdiff") or top_level_raw.get("gitdiff")
        if gitdiff and isinstance(gitdiff, str) and gitdiff.strip():
            patch_sources.append((gitdiff.strip(), "record.gitdiff", None))

        # Source 3: Assistant content containing unified diff blocks
        for event in list(events):
            if event.event_type == EventType.ASSISTANT_MESSAGE:
                for block in event.content:
                    if block.type == ContentType.TEXT and block.text:
                        diff_blocks = _extract_diff_blocks(block.text)
                        for diff_text in diff_blocks:
                            patch_sources.append(
                                (diff_text, f"event[{event.event_id}].content", event.event_id)
                            )

        # Process each patch source
        next_artifact_idx = len(artifacts)
        next_event_idx = max((e.idx for e in events), default=-1) + 1
        last_patch_artifact_id: str | None = None

        for diff_text, source_field, parent_event_id in patch_sources:
            paths, parse_ok = _parse_patch(diff_text)
            artifact_id = f"art_{next_artifact_idx:04d}"
            event_id = f"evt_patch_{next_artifact_idx:04d}"
            while event_id in existing_ids:
                next_artifact_idx += 1
                artifact_id = f"art_{next_artifact_idx:04d}"
                event_id = f"evt_patch_{next_artifact_idx:04d}"

            # Create artifact
            artifact = Artifact(
                artifact_id=artifact_id,
                kind=ArtifactKind.PATCH,
                content=diff_text,
                created_by_event_id=event_id,
                metadata={"source_field": source_field, "parse_ok": parse_ok},
            )
            artifacts.append(artifact)

            # Build state_delta with changed file paths
            state_delta: StateDelta | None = None
            if parse_ok and paths:
                state_delta = StateDelta(
                    writes=paths,
                    patch_artifact_id=artifact_id,
                )
            elif not parse_ok and _looks_like_diff(diff_text):
                # Still store as artifact but emit PARSE002 diagnostic
                diag = make_diagnostic(
                    DiagnosticCodes.PARSE002,
                    event_id=event_id,
                    field="content",
                    suggestion="Check for truncated or malformed diff headers",
                    source=Provenance(source_field=source_field, parser=self.name),
                )
                diagnostics.append(diag)
                state_delta = StateDelta(patch_artifact_id=artifact_id)
            elif not parse_ok:
                # Text doesn't even look like a diff, skip but warn
                diag = make_diagnostic(
                    DiagnosticCodes.PARSE002,
                    event_id=event_id,
                    field="content",
                    suggestion="Extracted text does not appear to be a valid diff",
                    source=Provenance(source_field=source_field, parser=self.name),
                )
                diagnostics.append(diag)
                state_delta = StateDelta(patch_artifact_id=artifact_id)

            # Create FILE_PATCH event
            patch_event = Event(
                event_id=event_id,
                idx=next_event_idx,
                event_type=EventType.FILE_PATCH,
                content=[
                    ContentBlock(type=ContentType.DIFF, text=diff_text, artifact_id=artifact_id)
                ],
                state_delta=state_delta,
                artifacts=[artifact_id],
                provenance=Provenance(
                    source_field=source_field,
                    parser=self.name,
                    confidence=1.0 if parse_ok else 0.5,
                ),
                raw={"source": source_field},
            )

            # Link to parent event if available
            if parent_event_id and parent_event_id in existing_ids:
                patch_event.parent_event_ids = [parent_event_id]

            events.append(patch_event)
            existing_ids.add(event_id)
            next_artifact_idx += 1
            next_event_idx += 1
            last_patch_artifact_id = artifact_id

        # Rebuild episodes with new events
        new_episodes: list[Episode] = []
        event_idx = 0
        for ep in record.episodes:
            ep_events = list(ep.events)
            new_episodes.append(
                Episode(
                    episode_id=ep.episode_id,
                    task_id=ep.task_id,
                    attempt_id=ep.attempt_id,
                    parent_episode_id=ep.parent_episode_id,
                    segments=ep.segments,
                    events=ep_events,
                    state_timeline=ep.state_timeline,
                    outcome=ep.outcome,
                    metadata=ep.metadata,
                )
            )

        # If there are patch events that weren't assigned to an episode, add to first episode
        patch_event_ids = {e.event_id for e in events if e.event_id.startswith("evt_patch_")}
        assigned_ids: set[str] = set()
        for ep in new_episodes:
            assigned_ids.update(e.event_id for e in ep.events)

        unassigned = [
            e for e in events if e.event_id in patch_event_ids and e.event_id not in assigned_ids
        ]
        if unassigned and new_episodes:
            first_ep = new_episodes[0]
            all_ep_events = list(first_ep.events) + unassigned
            new_episodes[0] = Episode(
                episode_id=first_ep.episode_id,
                task_id=first_ep.task_id,
                attempt_id=first_ep.attempt_id,
                parent_episode_id=first_ep.parent_episode_id,
                segments=first_ep.segments,
                events=all_ep_events,
                state_timeline=first_ep.state_timeline,
                outcome=first_ep.outcome,
                metadata=first_ep.metadata,
            )

        # Link final patch to outcome
        outcome = record.outcome
        if last_patch_artifact_id is not None and outcome is not None:
            outcome = outcome.model_copy(update={"final_patch_artifact_id": last_patch_artifact_id})
        elif last_patch_artifact_id is not None and outcome is None:
            from agentir.ir.outcome import Outcome

            outcome = Outcome(final_patch_artifact_id=last_patch_artifact_id)

        updated = record.model_copy(
            update={
                "episodes": new_episodes,
                "artifacts": artifacts,
                "outcome": outcome,
            }
        )

        return PassResult(record=updated, diagnostics=diagnostics)


register_pass(ExtractPatchesPass())
