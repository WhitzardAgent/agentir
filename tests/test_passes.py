"""Tests for the pass modules: parse, canonicalize, transform, verify.

Tests cover individual passes and the PassManager pipeline orchestration.
"""

from __future__ import annotations

from typing import Any

import pytest

from agentir.ir.action import Action
from agentir.ir.base import (
    ActionKind,
    ArtifactKind,
    CallStyle,
    ContentType,
    EventType,
    IRLevel,
    MessageRole,
    OutcomeStatus,
    PassKind,
    ReasoningPolicy,
    RedactionStatus,
    SideEffectLevel,
)
from agentir.ir.content import ContentBlock
from agentir.ir.episode import Episode
from agentir.ir.event import Event
from agentir.ir.outcome import Outcome
from agentir.ir.provenance import Provenance
from agentir.ir.record import AgentIRRecord
from agentir.ir.source import SourceRef
from agentir.ir.visibility import Visibility
from agentir.passes.base import PassContext, PassResult
from agentir.passes.manager import PassManager
from agentir.passes.registry import get_pass, list_passes


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_record(
    record_id: str = "rec-001",
    level: IRLevel = IRLevel.RAW,
    episodes: list[Episode] | None = None,
    raw: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    outcome: Outcome | None = None,
    artifacts: list[Any] | None = None,
) -> AgentIRRecord:
    """Build a minimal AgentIRRecord for pass testing."""
    return AgentIRRecord(
        record_id=record_id,
        level=level,
        source=SourceRef(dataset="test", framework="test-framework"),
        episodes=episodes or [],
        raw=raw or {},
        metadata=metadata or {},
        outcome=outcome,
        artifacts=artifacts or [],
    )


def _make_event(
    event_id: str,
    idx: int,
    event_type: EventType,
    role: MessageRole | None = None,
    content: list[ContentBlock] | None = None,
    action: Action | None = None,
    provenance: Provenance | None = None,
    visibility: Visibility | None = None,
    metadata: dict | None = None,
) -> Event:
    """Build a minimal Event for pass testing."""
    return Event(
        event_id=event_id,
        idx=idx,
        event_type=event_type,
        role=role,
        content=content or [],
        action=action,
        provenance=provenance,
        visibility=visibility or Visibility(),
        metadata=metadata or {},
    )


def _make_episode(
    episode_id: str = "ep-001",
    events: list[Event] | None = None,
) -> Episode:
    """Build a minimal Episode for pass testing."""
    return Episode(
        episode_id=episode_id,
        events=events or [],
    )


def _text_block(text: str) -> ContentBlock:
    """Shorthand for a plain-text ContentBlock."""
    return ContentBlock(type=ContentType.TEXT, text=text)


# ---------------------------------------------------------------------------
# ParseHermesXMLPass
# ---------------------------------------------------------------------------

from agentir.passes.parse_hermes_xml import ParseHermesXMLPass


class TestParseHermesXML:

    def test_extracts_tool_call_from_xml_block(self) -> None:
        content = '<tool_call>{"name": "bash", "arguments": {"cmd": "ls"}}</tool_call>'
        event = _make_event(
            event_id="evt-1", idx=0,
            event_type=EventType.ASSISTANT_MESSAGE,
            role=MessageRole.ASSISTANT,
            content=[_text_block(content)],
        )
        episode = _make_episode(events=[event])
        record = _make_record(episodes=[episode], level=IRLevel.RAW)
        pass_inst = ParseHermesXMLPass()
        result = pass_inst.run(record, PassContext())
        assert len(result.record.episodes) == 1
        events = result.record.episodes[0].events
        assert len(events) == 2
        tc_event = events[1]
        assert tc_event.event_type == EventType.TOOL_CALL
        assert tc_event.action is not None
        assert tc_event.action.kind == ActionKind.GENERIC_TOOL
        assert tc_event.action.tool_name == "bash"
        assert tc_event.action.arguments == {"cmd": "ls"}
        assert tc_event.action.call_style == CallStyle.XML_BLOCK
        assert tc_event.provenance is not None
        assert tc_event.provenance.parser == "parse-hermes-xml"
        assert tc_event.provenance.confidence == 1.0

    def test_extracts_multiple_tool_calls(self) -> None:
        content = (
            '<tool_call>{"name": "read", "arguments": {"path": "a.txt"}}</tool_call>\n'
            '<tool_call>{"name": "write", "arguments": {"path": "b.txt", "content": "hi"}}</tool_call>'
        )
        event = _make_event(
            event_id="evt-1", idx=0,
            event_type=EventType.ASSISTANT_MESSAGE,
            role=MessageRole.ASSISTANT,
            content=[_text_block(content)],
        )
        episode = _make_episode(events=[event])
        record = _make_record(episodes=[episode], level=IRLevel.RAW)
        pass_inst = ParseHermesXMLPass()
        result = pass_inst.run(record, PassContext())
        events = result.record.episodes[0].events
        assert len(events) == 3
        assert events[1].action.tool_name == "read"
        assert events[2].action.tool_name == "write"

    def test_non_assistant_events_unchanged(self) -> None:
        user_evt = _make_event(
            event_id="evt-u", idx=0,
            event_type=EventType.USER_MESSAGE,
            role=MessageRole.USER,
            content=[_text_block('<tool_call>{"name":"x"}</tool_call>')],
        )
        sys_evt = _make_event(
            event_id="evt-s", idx=1,
            event_type=EventType.SYSTEM_MESSAGE,
            role=MessageRole.SYSTEM,
            content=[_text_block("system")],
        )
        episode = _make_episode(events=[user_evt, sys_evt])
        record = _make_record(episodes=[episode], level=IRLevel.RAW)
        pass_inst = ParseHermesXMLPass()
        result = pass_inst.run(record, PassContext())
        events = result.record.episodes[0].events
        assert len(events) == 2

    def test_sets_level_to_parsed(self) -> None:
        event = _make_event(
            event_id="evt-1", idx=0,
            event_type=EventType.ASSISTANT_MESSAGE,
            role=MessageRole.ASSISTANT,
            content=[_text_block('<tool_call>{"name":"x"}</tool_call>')],
        )
        episode = _make_episode(events=[event])
        record = _make_record(episodes=[episode], level=IRLevel.RAW)
        pass_inst = ParseHermesXMLPass()
        result = pass_inst.run(record, PassContext())
        assert result.record.level == "parsed"


# ---------------------------------------------------------------------------
# PairToolResultsPass
# ---------------------------------------------------------------------------

from agentir.passes.pair_tool_results import PairToolResultsPass


class TestPairToolResults:

    def test_pairs_by_tool_call_id(self) -> None:
        call = _make_event(
            event_id="tc-1", idx=1,
            event_type=EventType.TOOL_CALL,
            action=Action(
                kind=ActionKind.GENERIC_TOOL,
                tool_name="bash",
                tool_call_id="call_123",
                call_style=CallStyle.NATIVE_TOOL_CALL,
            ),
        )
        result = _make_event(
            event_id="tr-1", idx=2,
            event_type=EventType.TOOL_RESULT,
        )
        episode = _make_episode(events=[call, result])
        record = _make_record(episodes=[episode])
        pass_inst = PairToolResultsPass()
        result_ctx = pass_inst.run(record, PassContext())
        events = result_ctx.record.episodes[0].events
        assert len(events) == 2
        tc = events[0]
        tr = events[1]
        assert tc.child_event_ids == ["tr-1"]
        assert tr.parent_event_ids == ["tc-1"]

    def test_diagnostic_for_unmatched_tool_call(self) -> None:
        call = _make_event(
            event_id="tc-1", idx=1,
            event_type=EventType.TOOL_CALL,
            action=Action(
                kind=ActionKind.GENERIC_TOOL,
                tool_name="bash",
                tool_call_id="call_orphan",
            ),
        )
        episode = _make_episode(events=[call])
        record = _make_record(episodes=[episode])
        pass_inst = PairToolResultsPass()
        result = pass_inst.run(record, PassContext())
        assert any(d.code == "PAIR001" for d in result.diagnostics)

    def test_diagnostic_for_unmatched_tool_result(self) -> None:
        result = _make_event(
            event_id="tr-1", idx=0,
            event_type=EventType.TOOL_RESULT,
            metadata={"tool_call_id": "call_missing"},
        )
        episode = _make_episode(events=[result])
        record = _make_record(episodes=[episode])
        pass_inst = PairToolResultsPass()
        result_ctx = pass_inst.run(record, PassContext())
        assert any(d.code == "PAIR002" for d in result_ctx.diagnostics)


# ---------------------------------------------------------------------------
# ExtractPatchesPass
# ---------------------------------------------------------------------------

from agentir.passes.extract_patches import ExtractPatchesPass


class TestExtractPatches:

    def test_extracts_diff_from_raw_gitdiff_field(self) -> None:
        diff_text = (
            "diff --git a/foo.py b/foo.py\n"
            "index abc..def 100644\n"
            "--- a/foo.py\n"
            "+++ b/foo.py\n"
            "@@ -1,3 +1,3 @@\n"
            " line1\n"
            "-old\n"
            "+new\n"
            " line3\n"
        )
        record = _make_record(
            episodes=[_make_episode(events=[])],
            raw={"gitdiff": diff_text},
        )
        pass_inst = ExtractPatchesPass()
        result = pass_inst.run(record, PassContext())
        assert len(result.record.artifacts) > 0
        artifact = result.record.artifacts[0]
        assert artifact.kind == ArtifactKind.PATCH
        assert artifact.content is not None
        assert "diff --git" in artifact.content

    def test_creates_file_patch_event(self) -> None:
        diff_text = (
            "diff --git a/file.py b/file.py\n"
            "--- a/file.py\n"
            "+++ b/file.py\n"
            "@@ -1 +1 @@\n"
            "-x\n"
            "+y\n"
        )
        episode = _make_episode(
            events=[
                _make_event(
                    event_id="evt-0", idx=0,
                    event_type=EventType.ASSISTANT_MESSAGE,
                    role=MessageRole.ASSISTANT,
                    content=[_text_block(diff_text)],
                ),
            ],
        )
        record = _make_record(episodes=[episode])
        pass_inst = ExtractPatchesPass()
        result = pass_inst.run(record, PassContext())
        all_events = []
        for ep in result.record.episodes:
            all_events.extend(ep.events)
        patch_events = [e for e in all_events if e.event_type == EventType.FILE_PATCH]
        assert len(patch_events) > 0
        pe = patch_events[0]
        assert pe.state_delta is not None
        assert pe.state_delta.patch_artifact_id is not None


# ---------------------------------------------------------------------------
# NormalizeOutcomePass
# ---------------------------------------------------------------------------

from agentir.passes.normalize_outcome import NormalizeOutcomePass


class TestNormalizeOutcome:

    def test_extracts_reward_from_agenttrove_metadata(self) -> None:
        record = _make_record(metadata={"reward": 0.85})
        pass_inst = NormalizeOutcomePass()
        result = pass_inst.run(record, PassContext())
        assert result.record.outcome is not None
        assert result.record.outcome.reward == 0.85

    def test_extracts_passed_from_openhands_metadata(self) -> None:
        record = _make_record(metadata={"success": True})
        pass_inst = NormalizeOutcomePass()
        result = pass_inst.run(record, PassContext())
        assert result.record.outcome.passed is True

    def test_detects_reward_passed_conflict(self) -> None:
        record = _make_record(metadata={"reward": 1.0, "success": False})
        pass_inst = NormalizeOutcomePass()
        result = pass_inst.run(record, PassContext())
        assert any(d.code == "OUTCOME001" for d in result.diagnostics)

    def test_derives_partial_from_reward_only(self) -> None:
        record = _make_record(metadata={"reward": 0.5})
        pass_inst = NormalizeOutcomePass()
        result = pass_inst.run(record, PassContext())
        assert result.record.outcome.status == OutcomeStatus.PARTIAL

    def test_derives_success_from_passed(self) -> None:
        record = _make_record(metadata={"success": True})
        pass_inst = NormalizeOutcomePass()
        result = pass_inst.run(record, PassContext())
        assert result.record.outcome.status == OutcomeStatus.SUCCESS


# ---------------------------------------------------------------------------
# RedactReasoningPass
# ---------------------------------------------------------------------------

from agentir.passes.redact_reasoning import RedactReasoningPass


class TestRedactReasoning:

    def _reasoning_record(self) -> AgentIRRecord:
        event = _make_event(
            event_id="re-1", idx=0,
            event_type=EventType.REASONING,
            content=[_text_block("I should use read_file first.")],
        )
        episode = _make_episode(events=[event])
        return _make_record(episodes=[episode])

    def test_drop_policy_clears_content_and_sets_untrainable(self) -> None:
        record = self._reasoning_record()
        ctx = PassContext(reasoning_policy="drop")
        pass_inst = RedactReasoningPass()
        result = pass_inst.run(record, ctx)
        evt = result.record.episodes[0].events[0]
        assert evt.content == []
        assert evt.visibility.trainable is False

    def test_redact_policy_replaces_content_with_placeholder(self) -> None:
        record = self._reasoning_record()
        ctx = PassContext(reasoning_policy="redact")
        pass_inst = RedactReasoningPass()
        result = pass_inst.run(record, ctx)
        evt = result.record.episodes[0].events[0]
        assert len(evt.content) == 1
        assert evt.content[0].text == "[REDACTED_REASONING]"
        assert evt.visibility.redaction_status == RedactionStatus.REDACTED

    def test_metadata_only_policy_clears_content(self) -> None:
        record = self._reasoning_record()
        ctx = PassContext(reasoning_policy="metadata_only")
        pass_inst = RedactReasoningPass()
        result = pass_inst.run(record, ctx)
        evt = result.record.episodes[0].events[0]
        assert evt.content == []
        assert evt.visibility.redaction_status == RedactionStatus.METADATA_ONLY

    def test_summarize_policy_replaces_with_placeholder(self) -> None:
        record = self._reasoning_record()
        ctx = PassContext(reasoning_policy="summarize")
        pass_inst = RedactReasoningPass()
        result = pass_inst.run(record, ctx)
        evt = result.record.episodes[0].events[0]
        assert len(evt.content) == 1
        assert "REASONING_SUMMARY" in evt.content[0].text

    def test_non_reasoning_events_untouched(self) -> None:
        user_evt = _make_event(
            event_id="u-1", idx=0,
            event_type=EventType.USER_MESSAGE,
            content=[_text_block("hello")],
        )
        reasoning_evt = _make_event(
            event_id="re-1", idx=1,
            event_type=EventType.REASONING,
            content=[_text_block("think...")],
        )
        episode = _make_episode(events=[user_evt, reasoning_evt])
        record = _make_record(episodes=[episode])
        ctx = PassContext(reasoning_policy="drop")
        pass_inst = RedactReasoningPass()
        result = pass_inst.run(record, ctx)
        events = result.record.episodes[0].events
        assert events[0].content[0].text == "hello"
        assert events[1].content == []


# ---------------------------------------------------------------------------
# VerifyPass
# ---------------------------------------------------------------------------

from agentir.passes.verify import VerifyPass


class TestVerify:

    def test_catches_duplicate_event_ids(self) -> None:
        e1 = _make_event(event_id="dup", idx=0, event_type=EventType.USER_MESSAGE)
        e2 = _make_event(event_id="dup", idx=1, event_type=EventType.ASSISTANT_MESSAGE)
        episode = _make_episode(events=[e1, e2])
        record = _make_record(episodes=[episode])
        pass_inst = VerifyPass()
        result = pass_inst.run(record, PassContext())
        assert any(d.code == "VERIFY001" for d in result.diagnostics)

    def test_allows_unique_event_ids(self) -> None:
        e1 = _make_event(event_id="a", idx=0, event_type=EventType.USER_MESSAGE)
        e2 = _make_event(event_id="b", idx=1, event_type=EventType.ASSISTANT_MESSAGE)
        episode = _make_episode(events=[e1, e2])
        record = _make_record(episodes=[episode])
        pass_inst = VerifyPass()
        result = pass_inst.run(record, PassContext())
        assert not any(d.code == "VERIFY001" for d in result.diagnostics)

    def test_checks_monotonic_indices(self) -> None:
        e1 = _make_event(event_id="a", idx=5, event_type=EventType.USER_MESSAGE)
        e2 = _make_event(event_id="b", idx=3, event_type=EventType.ASSISTANT_MESSAGE)
        episode = _make_episode(events=[e1, e2])
        record = _make_record(episodes=[episode])
        pass_inst = VerifyPass()
        result = pass_inst.run(record, PassContext())
        assert any(
            d.code == "VERIFY001" and d.field == "idx"
            for d in result.diagnostics
        )


# ---------------------------------------------------------------------------
# PassManager pipeline
# ---------------------------------------------------------------------------


class TestPassManager:

    def test_runs_multiple_passes_in_sequence(self) -> None:
        content = (
            '<tool_call>{"name": "bash", "arguments": {"cmd": "ls"}}</tool_call>\n'
            '<tool_call>{"name": "bash", "arguments": {"cmd": "pwd"}}</tool_call>'
        )
        event = _make_event(
            event_id="evt-1", idx=0,
            event_type=EventType.ASSISTANT_MESSAGE,
            role=MessageRole.ASSISTANT,
            content=[_text_block(content)],
        )
        episode = _make_episode(events=[event])
        record = _make_record(
            episodes=[episode],
            level=IRLevel.RAW,
            metadata={"reward": 1.0, "success": True},
        )
        manager = PassManager()
        pipeline = ["parse-hermes-xml", "pair-tool-results", "normalize-outcome"]
        ctx = PassContext(strict=False)
        result = manager.run_pipeline(record, pipeline, ctx)
        assert isinstance(result, PassResult)
        assert result.record is not None
        events = result.record.episodes[0].events
        tc_events = [e for e in events if e.event_type == EventType.TOOL_CALL]
        assert len(tc_events) >= 2
        assert result.record.outcome is not None

    def test_unknown_pass_raises_value_error(self) -> None:
        record = _make_record()
        manager = PassManager()
        ctx = PassContext()
        with pytest.raises(ValueError, match="Unknown pass"):
            manager.run_pipeline(record, ["nonexistent-pass"], ctx)


# ---------------------------------------------------------------------------
# Registry tests
# ---------------------------------------------------------------------------


class TestPassRegistry:

    def test_get_pass_returns_instance(self) -> None:
        p = get_pass("parse-hermes-xml")
        assert p is not None
        assert p.name == "parse-hermes-xml"
        assert p.kind == PassKind.PARSE

    def test_get_pass_returns_none_for_unknown(self) -> None:
        assert get_pass("nonexistent-pass") is None

    def test_list_passes_includes_known_passes(self) -> None:
        names = list_passes()
        expected = {
            "parse-hermes-xml",
            "pair-tool-results",
            "extract-patches",
            "normalize-outcome",
            "redact-reasoning",
            "verify",
        }
        missing = expected - set(names)
        assert not missing, f"Missing passes from registry: {missing}"
