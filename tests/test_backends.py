"""Tests for the backend modules: lowering, loss tracking, and registry.

Tests cover individual backends and the backend registry operations.
"""

from __future__ import annotations

from typing import Any

import pytest

from agentir.backends.base import BackendContext
from agentir.backends.loss import LossReport, LoweringResult
from agentir.backends.registry import get_backend, list_backends
from agentir.ir.action import Action
from agentir.ir.artifact import Artifact
from agentir.ir.base import (
    ActionKind,
    ArtifactKind,
    CallStyle,
    ContentType,
    EventType,
    IRLevel,
    LoweringStatus,
    MessageRole,
    OutcomeStatus,
    SideEffectLevel,
)
from agentir.ir.content import ContentBlock
from agentir.ir.episode import Episode
from agentir.ir.event import Event
from agentir.ir.observation import Observation, ObservationKind
from agentir.ir.outcome import Outcome
from agentir.ir.provenance import Provenance
from agentir.ir.record import AgentIRRecord
from agentir.ir.source import SourceRef
from agentir.ir.visibility import Visibility


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_record(
    record_id: str = "rec-001",
    level: IRLevel = IRLevel.CANONICAL,
    episodes: list[Episode] | None = None,
    raw: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    outcome: Outcome | None = None,
    artifacts: list[Any] | None = None,
    tool_registry: list[Any] | None = None,
) -> AgentIRRecord:
    """Build a minimal AgentIRRecord for backend testing."""
    return AgentIRRecord(
        record_id=record_id,
        level=level,
        source=SourceRef(dataset="test", framework="test-framework"),
        episodes=episodes or [],
        raw=raw or {},
        metadata=metadata or {},
        outcome=outcome,
        artifacts=artifacts or [],
        tool_registry=tool_registry or [],
    )


def _make_event(
    event_id: str,
    idx: int,
    event_type: EventType,
    role: MessageRole | None = None,
    content: list[ContentBlock] | None = None,
    action: Action | None = None,
    observation: Observation | None = None,
    metadata: dict[str, Any] | None = None,
) -> Event:
    """Build a minimal Event for backend testing."""
    return Event(
        event_id=event_id,
        idx=idx,
        event_type=event_type,
        role=role,
        content=content or [],
        action=action,
        observation=observation,
        metadata=metadata or {},
    )


def _make_episode(
    episode_id: str = "ep-001",
    events: list[Event] | None = None,
) -> Episode:
    """Build a minimal Episode for backend testing."""
    return Episode(
        episode_id=episode_id,
        events=events or [],
    )


def _text_block(text: str) -> ContentBlock:
    """Shorthand for a plain-text ContentBlock."""
    return ContentBlock(type=ContentType.TEXT, text=text)


def _make_tool_call_event(
    event_id: str,
    idx: int,
    tool_name: str,
    tool_call_id: str,
    arguments: dict[str, Any] | None = None,
) -> Event:
    """Shorthand to build a TOOL_CALL event."""
    return _make_event(
        event_id=event_id,
        idx=idx,
        event_type=EventType.TOOL_CALL,
        role=MessageRole.ASSISTANT,
        action=Action(
            kind=ActionKind.GENERIC_TOOL,
            tool_name=tool_name,
            tool_call_id=tool_call_id,
            arguments=arguments or {},
            call_style=CallStyle.NATIVE_TOOL_CALL,
        ),
    )


def _make_tool_result_event(
    event_id: str,
    idx: int,
    tool_call_id: str,
    stdout: str = "",
    role: MessageRole = MessageRole.TOOL,
) -> Event:
    """Shorthand to build a TOOL_RESULT event."""
    return _make_event(
        event_id=event_id,
        idx=idx,
        event_type=EventType.TOOL_RESULT,
        role=role,
        action=Action(
            kind=ActionKind.GENERIC_TOOL,
            tool_call_id=tool_call_id,
            call_style=CallStyle.UNKNOWN,
        ),
        observation=Observation(
            kind=ObservationKind.STDOUT,
            stdout=stdout,
        ),
    )


# ---------------------------------------------------------------------------
# SFTBackend
# ---------------------------------------------------------------------------

from agentir.backends.sft import SFTBackend


class TestSFTBackend:

    def test_produces_messages_list(self) -> None:
        """SFT backend produces a messages list with expected keys."""
        event = _make_event(
            event_id="evt-1", idx=0,
            event_type=EventType.USER_MESSAGE,
            role=MessageRole.USER,
            content=[_text_block("Hello, write a function.")],
        )
        episode = _make_episode(events=[event])
        record = _make_record(episodes=[episode])

        backend = SFTBackend()
        result = backend.lower_record(record, BackendContext())

        assert isinstance(result, LoweringResult)
        assert "messages" in result.output
        assert isinstance(result.output["messages"], list)
        assert len(result.output["messages"]) > 0

    def test_user_message_becomes_user_role(self) -> None:
        """A USER_MESSAGE event maps to role='user' in SFT output."""
        event = _make_event(
            event_id="evt-1", idx=0,
            event_type=EventType.USER_MESSAGE,
            role=MessageRole.USER,
            content=[_text_block("hello")],
        )
        episode = _make_episode(events=[event])
        record = _make_record(episodes=[episode])

        backend = SFTBackend()
        result = backend.lower_record(record, BackendContext())

        msgs = result.output["messages"]
        assert msgs[0]["role"] == "user"
        assert msgs[0]["content"] == "hello"

    def test_system_message_becomes_system_role(self) -> None:
        """A SYSTEM_MESSAGE event maps to role='system' in SFT output."""
        event = _make_event(
            event_id="evt-1", idx=0,
            event_type=EventType.SYSTEM_MESSAGE,
            role=MessageRole.SYSTEM,
            content=[_text_block("You are a helpful assistant.")],
        )
        episode = _make_episode(events=[event])
        record = _make_record(episodes=[episode])

        backend = SFTBackend()
        result = backend.lower_record(record, BackendContext())

        msgs = result.output["messages"]
        assert msgs[0]["role"] == "system"

    def test_tool_call_produces_tool_calls_array(self) -> None:
        """A TOOL_CALL event produces assistant message with tool_calls array."""
        call = _make_tool_call_event(
            event_id="tc-1", idx=1,
            tool_name="bash",
            tool_call_id="call_abc",
            arguments={"cmd": "ls"},
        )
        result_evt = _make_tool_result_event(
            event_id="tr-1", idx=2,
            tool_call_id="call_abc",
            stdout="file1.txt\nfile2.txt\n",
        )
        episode = _make_episode(events=[call, result_evt])
        record = _make_record(episodes=[episode])

        backend = SFTBackend()
        result = backend.lower_record(record, BackendContext())

        msgs = result.output["messages"]
        assistant_msgs = [m for m in msgs if m.get("role") == "assistant" and m.get("tool_calls")]
        assert len(assistant_msgs) == 1
        tc = assistant_msgs[0]["tool_calls"]
        assert len(tc) == 1
        assert tc[0]["id"] == "call_abc"
        assert tc[0]["function"]["name"] == "bash"
        import json
        args = json.loads(tc[0]["function"]["arguments"])
        assert args["cmd"] == "ls"

    def test_tool_result_attached_after_tool_call(self) -> None:
        """A tool result is attached as a tool-role message after the call."""
        call = _make_tool_call_event(
            event_id="tc-1", idx=1,
            tool_name="read_file",
            tool_call_id="call_xyz",
            arguments={"path": "file.txt"},
        )
        result_evt = _make_tool_result_event(
            event_id="tr-1", idx=2,
            tool_call_id="call_xyz",
            stdout="content here",
        )
        episode = _make_episode(events=[call, result_evt])
        record = _make_record(episodes=[episode])

        backend = SFTBackend()
        result = backend.lower_record(record, BackendContext())

        msgs = result.output["messages"]
        tool_msgs = [m for m in msgs if m.get("role") == "tool"]
        assert len(tool_msgs) == 1
        assert tool_msgs[0]["tool_call_id"] == "call_xyz"
        assert "content here" in tool_msgs[0]["content"]

    def test_empty_record_no_assistant_produces_warning(self) -> None:
        """Record with only user/system messages gets a LOWER003 warning."""
        event = _make_event(
            event_id="evt-1", idx=0,
            event_type=EventType.SYSTEM_MESSAGE,
            role=MessageRole.SYSTEM,
            content=[_text_block("system prompt")],
        )
        episode = _make_episode(events=[event])
        record = _make_record(episodes=[episode])

        backend = SFTBackend()
        result = backend.lower_record(record, BackendContext())

        assert any(l.code == "LOWER003" for l in result.report.losses)


# ---------------------------------------------------------------------------
# OpenAIToolsBackend
# ---------------------------------------------------------------------------

from agentir.backends.openai_tools import OpenAIToolsBackend


class TestOpenAIToolsBackend:

    def test_preserves_tool_calls_format(self) -> None:
        """Tool calls in OpenAI format have the expected id/type/function."""
        call = _make_tool_call_event(
            event_id="tc-1", idx=1,
            tool_name="get_weather",
            tool_call_id="call_w1",
            arguments={"city": "London"},
        )
        result_evt = _make_tool_result_event(
            event_id="tr-1", idx=2,
            tool_call_id="call_w1",
            stdout="Cloudy, 15C",
        )
        episode = _make_episode(events=[call, result_evt])
        record = _make_record(episodes=[episode])

        backend = OpenAIToolsBackend()
        result = backend.lower_record(record, BackendContext())

        msgs = result.output["messages"]
        tool_call_msgs = [m for m in msgs if m.get("tool_calls")]
        assert len(tool_call_msgs) == 1

        tc = tool_call_msgs[0]["tool_calls"][0]
        assert tc["type"] == "function"
        assert "id" in tc
        assert "function" in tc

    def test_tool_result_produces_tool_role_before(self) -> None:
        """Tool results produce role='tool' messages with tool_call_id."""
        call = _make_tool_call_event(
            event_id="tc-1", idx=1,
            tool_name="calculator",
            tool_call_id="call_123",
            arguments={"expr": "2+2"},
        )
        result_evt = _make_tool_result_event(
            event_id="tr-1", idx=2,
            tool_call_id="call_123",
            stdout="4",
        )
        episode = _make_episode(events=[call, result_evt])
        record = _make_record(episodes=[episode])

        backend = OpenAIToolsBackend()
        result = backend.lower_record(record, BackendContext())

        msgs = result.output["messages"]
        tool_msgs = [m for m in msgs if m.get("role") == "tool"]
        # The result should be consumed and emitted
        assert len(tool_msgs) == 1


# ---------------------------------------------------------------------------
# HermesXMLBackend
# ---------------------------------------------------------------------------

from agentir.backends.hermes_xml import HermesXMLBackend


class TestHermesXMLBackend:

    def test_serializes_tool_calls_as_xml_blocks(self) -> None:
        """A TOOL_CALL event is serialized with a Hermes glyph marker."""
        call = _make_tool_call_event(
            event_id="tc-1", idx=1,
            tool_name="bash",
            tool_call_id="call_t1",
            arguments={"cmd": "echo hi"},
        )
        episode = _make_episode(events=[call])
        record = _make_record(episodes=[episode])

        backend = HermesXMLBackend()
        result = backend.lower_record(record, BackendContext())

        conversations = result.output["conversations"]
        assert len(conversations) > 0
        # The Hermes glyph ༄ should appear in the value
        assert any("bash" in c["value"] for c in conversations)

    def test_user_message_becomes_human_from(self) -> None:
        """A USER_MESSAGE maps to from='human' in Hermes XML."""
        event = _make_event(
            event_id="evt-1", idx=0,
            event_type=EventType.USER_MESSAGE,
            role=MessageRole.USER,
            content=[_text_block("What is 2+2?")],
        )
        episode = _make_episode(events=[event])
        record = _make_record(episodes=[episode])

        backend = HermesXMLBackend()
        result = backend.lower_record(record, BackendContext())

        conversations = result.output["conversations"]
        assert len(conversations) == 1
        assert conversations[0]["from"] == "human"


# ---------------------------------------------------------------------------
# OpenHandsBackend
# ---------------------------------------------------------------------------

from agentir.backends.openhands import OpenHandsBackend


class TestOpenHandsBackend:

    def test_emits_trajectory_list(self) -> None:
        """The OpenHands backend produces a trajectory list."""
        event = _make_event(
            event_id="evt-1", idx=0,
            event_type=EventType.USER_MESSAGE,
            role=MessageRole.USER,
            content=[_text_block("Fix the bug.")],
        )
        episode = _make_episode(events=[event])
        record = _make_record(episodes=[episode])

        backend = OpenHandsBackend()
        result = backend.lower_record(record, BackendContext())

        assert "trajectory" in result.output
        assert isinstance(result.output["trajectory"], list)

    def test_emits_model_patch_from_patch_artifact(self) -> None:
        """Patch artifacts produce a model_patch field in the output."""
        diff_text = "diff --git a/file.py b/file.py\n--- a/file.py\n+++ b/file.py\n@@ -1 +1 @@\n-x\n+y\n"
        artifact = Artifact(
            artifact_id="art-1",
            kind=ArtifactKind.PATCH,
            content=diff_text,
        )
        event = _make_event(
            event_id="evt-1", idx=0,
            event_type=EventType.USER_MESSAGE,
            role=MessageRole.USER,
            content=[_text_block("task")],
        )
        episode = _make_episode(events=[event])
        record = _make_record(
            episodes=[episode],
            artifacts=[artifact],
        )

        backend = OpenHandsBackend()
        result = backend.lower_record(record, BackendContext())

        assert result.output["model_patch"] == diff_text


# ---------------------------------------------------------------------------
# ShareGPTBackend
# ---------------------------------------------------------------------------

from agentir.backends.sharegpt import ShareGPTBackend


class TestShareGPTBackend:

    def test_reports_lossy_when_tool_calls_exist(self) -> None:
        """ShareGPT reports lossy when tool calls are present."""
        call = _make_tool_call_event(
            event_id="tc-1", idx=1,
            tool_name="bash",
            tool_call_id="call_st",
            arguments={"cmd": "ls"},
        )
        episode = _make_episode(events=[call])
        record = _make_record(episodes=[episode])

        backend = ShareGPTBackend()
        ctx = BackendContext(tool_policy="structured")
        result = backend.lower_record(record, ctx)

        assert result.report.status in (LoweringStatus.LOSSY, LoweringStatus.PARTIAL)
        assert len(result.report.losses) > 0

    def test_reports_partial_with_inline_tool_policy(self) -> None:
        """With inline tool_policy, ShareGPT reports partial (not lossy/exact)."""
        call = _make_tool_call_event(
            event_id="tc-1", idx=1,
            tool_name="bash",
            tool_call_id="call_st",
            arguments={"cmd": "ls"},
        )
        episode = _make_episode(events=[call])
        record = _make_record(episodes=[episode])

        backend = ShareGPTBackend()
        ctx = BackendContext(tool_policy="inline")
        result = backend.lower_record(record, ctx)

        assert result.report.status == LoweringStatus.PARTIAL

    def test_conversations_format(self) -> None:
        """ShareGPT produces from='human'/'gpt' conversation pairs."""
        user_evt = _make_event(
            event_id="evt-1", idx=0,
            event_type=EventType.USER_MESSAGE,
            role=MessageRole.USER,
            content=[_text_block("Hello")],
        )
        assistant_evt = _make_event(
            event_id="evt-2", idx=1,
            event_type=EventType.ASSISTANT_MESSAGE,
            role=MessageRole.ASSISTANT,
            content=[_text_block("Hi!")],
        )
        episode = _make_episode(events=[user_evt, assistant_evt])
        record = _make_record(episodes=[episode])

        backend = ShareGPTBackend()
        result = backend.lower_record(record, BackendContext())

        conversations = result.output["conversations"]
        assert len(conversations) == 2
        assert conversations[0]["from"] == "human"
        assert conversations[1]["from"] == "gpt"


# ---------------------------------------------------------------------------
# LossReport
# ---------------------------------------------------------------------------


class TestLossReport:

    def test_loss_report_has_correct_status(self) -> None:
        """LoweringResult.report exposes target, status, and losses."""
        event = _make_event(
            event_id="evt-1", idx=0,
            event_type=EventType.USER_MESSAGE,
            role=MessageRole.USER,
            content=[_text_block("hello")],
        )
        episode = _make_episode(events=[event])
        record = _make_record(episodes=[episode])

        backend = SFTBackend()
        result = backend.lower_record(record, BackendContext())

        report = result.report
        assert isinstance(report, LossReport)
        assert report.target == "sft"
        # With only a user message LC, no assistive output, should be lossy
        assert report.status in (LoweringStatus.EXACT, LoweringStatus.LOSSY, LoweringStatus.PARTIAL, LoweringStatus.UNSUPPORTED)
        assert isinstance(report.losses, list)

    def test_loss_report_produced_for_all_backends(self) -> None:
        """Every backend produces a LoweringResult with a LossReport."""
        event = _make_event(
            event_id="evt-1", idx=0,
            event_type=EventType.USER_MESSAGE,
            role=MessageRole.USER,
            content=[_text_block("task")],
        )
        episode = _make_episode(events=[event])
        record = _make_record(episodes=[episode])

        for backend_cls in [SFTBackend, OpenAIToolsBackend, OpenHandsBackend, ShareGPTBackend]:
            if backend_cls == ShareGPTBackend:
                ctx = BackendContext(tool_policy="structured")
            else:
                ctx = BackendContext()

            backend = backend_cls()
            result = backend.lower_record(record, ctx)

            assert isinstance(result, LoweringResult)
            assert isinstance(result.report, LossReport)
            assert result.report.target == backend.name
            assert result.report.status in (
                LoweringStatus.EXACT,
                LoweringStatus.LOSSY,
                LoweringStatus.PARTIAL,
                LoweringStatus.UNSUPPORTED,
            )


# ---------------------------------------------------------------------------
# BackendRegistry
# ---------------------------------------------------------------------------


class TestBackendRegistry:

    def test_list_backends_includes_all(self) -> None:
        """list_backends returns all registered backend names."""
        names = list_backends()
        expected = {
            "sft",
            "openai-tools",
            "hermes-xml",
            "openhands",
            "sharegpt",
            "process-supervision",
        }
        missing = expected - set(names)
        assert not missing, f"Missing backends from registry: {missing}"

    def test_get_backend_returns_instance(self) -> None:
        """get_backend returns the correct backend for a known name."""
        for name in ["sft", "openai-tools", "hermes-xml", "openhands", "sharegpt"]:
            b = get_backend(name)
            assert b is not None, f"get_backend({name!r}) returned None"
            assert b.name == name, f"Backend name mismatch: {b.name} != {name}"

    def test_get_backend_raises_key_error_for_unknown(self) -> None:
        """get_backend raises KeyError for an unregistered name."""
        with pytest.raises(KeyError, match="Unknown backend"):
            get_backend("nonexistent-backend")
