"""Comprehensive tests for AgentIR intermediate representation models.

Covers construction, serialization, validation, enums, and edge cases across
all model classes in agentir.ir.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from pydantic import ValidationError

from agentir.ir import (
    Action,
    ActionKind,
    ActorKind,
    ActorSpec,
    AgentIRRecord,
    Artifact,
    ArtifactKind,
    CallStyle,
    ContentBlock,
    ContentType,
    ControlFlow,
    ControlInfo,
    DiagnosticSeverity,
    EnvironmentSpec,
    Episode,
    Event,
    EventType,
    FailureReason,
    IRLevel,
    MessageRole,
    Observation,
    ObservationKind,
    Outcome,
    OutcomeStatus,
    Provenance,
    ReasoningPolicy,
    RedactionStatus,
    Segment,
    SegmentKind,
    SideEffectLevel,
    SourceRef,
    StateDelta,
    StateSnapshot,
    TaskSpec,
    ToolSpec,
    VerifierResult,
    Visibility,
)


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------

def _make_source_ref(dataset: str = "swiftbench") -> SourceRef:
    return SourceRef(
        dataset=dataset,
        dataset_url="https://datasets.example.org/v1",
        config="default",
        split="test",
        row_id="42",
        row_index=42,
        framework="claude-code",
        framework_version="4.0.x",
        format="jsonl",
        license="mit",
        original_source="internal-tracker",
        original_teacher="claude-4-coder",
    )


def _make_task_spec() -> TaskSpec:
    return TaskSpec(
        task_id="task-001",
        instruction="Fix the off-by-one error in binsearch.py",
        category="bugfix",
        subcategory="off_by_one",
        benchmark="swebenchpro",
        repo="org/repo",
        base_commit="abc1234def",
        issue_id="gh-9999",
        environment=EnvironmentSpec(
            kind="docker",
            cwd="/workspace",
            image="python:3.12",
        ),
        metadata={"difficulty": "easy"},
    )


def _make_tool_spec(name: str = "bash", tool_id: str = "tool-01") -> ToolSpec:
    return ToolSpec(
        tool_id=tool_id,
        name=name,
        description="Execute a bash command",
        input_schema={"type": "object", "properties": {"cmd": {"type": "string"}}},
        source="internal",
        normalized_name=name,
    )


def _make_actor_spec(
    actor_id: str = "actor-01",
    kind: ActorKind = ActorKind.ASSISTANT,
) -> ActorSpec:
    return ActorSpec(
        actor_id=actor_id,
        kind=kind,
        name="Claude 4 Code",
        model="claude-4-coder",
        role="assistant",
        metadata={"provider": "anthropic"},
    )


def _make_provenance() -> Provenance:
    return Provenance(
        dataset="swiftbench",
        config="default",
        split="test",
        row_id="42",
        source_field="messages",
        row_index=42,
        char_start=0,
        char_end=256,
        parser="claude-code-v4-parser",
        confidence=0.98,
    )


def _make_visibility() -> Visibility:
    return Visibility(
        trainable=True,
        contains_reasoning=True,
        contains_sensitive=False,
        redaction_status=RedactionStatus.NONE,
        policy=ReasoningPolicy.PRESERVE,
    )


def _make_content_block(
    type_: ContentType = ContentType.TEXT,
    text: str = "I will fix the bug.",
) -> ContentBlock:
    return ContentBlock(type=type_, text=text)


def _make_action(kind: ActionKind = ActionKind.GENERIC_TOOL) -> Action:
    return Action(
        kind=kind,
        tool_name="bash",
        tool_call_id="call-abc123",
        arguments={"cmd": "pytest tests/test_binsearch.py"},
        normalized_arguments={"cmd": "pytest tests/test_binsearch.py"},
        call_style=CallStyle.NATIVE_TOOL_CALL,
        side_effect_level=SideEffectLevel.WORKSPACE_WRITE,
        timeout_seconds=120.0,
    )


def _make_observation(
    kind: ObservationKind = ObservationKind.TOOL_JSON,
) -> Observation:
    return Observation(
        kind=kind,
        content=[_make_content_block(ContentType.JSON, '{"passed": true}')],
        exit_code=0,
        truncated=False,
        artifact_ids=["artifact-01"],
        metadata={"elapsed_ms": 142},
    )


def _make_control_info() -> ControlInfo:
    return ControlInfo(
        flow=ControlFlow.SEQUENCE,
        block_id="block-01",
        next_event_ids=["evt-002"],
        metadata={"position": "step_3_of_5"},
    )


def _make_event(
    event_id: str = "evt-001",
    idx: int = 0,
    event_type: EventType = EventType.TOOL_CALL,
    *,
    with_action: bool = True,
    with_observation: bool = False,
) -> Event:
    return Event(
        event_id=event_id,
        idx=idx,
        event_type=event_type,
        actor_id="actor-01",
        role=MessageRole.ASSISTANT,
        parent_event_ids=[],
        child_event_ids=["evt-002"],
        segment_id="seg-01",
        timestamp=datetime.now(timezone.utc).isoformat(),
        content=[_make_content_block()],
        action=_make_action() if with_action else None,
        observation=_make_observation() if with_observation else None,
        state_delta=StateDelta(
            reads=["tests/test_binsearch.py"],
            writes=["__pycache__/test_binsearch.pytest_cache"],
        ),
        control=_make_control_info(),
        artifacts=["artifact-01"],
        provenance=_make_provenance(),
        visibility=_make_visibility(),
        raw={"raw_tool_json": '{"cmd":"..."}'},
    )


def _make_diagnostic() -> Any:
    from agentir.diagnostics.diagnostic import Diagnostic
    return Diagnostic(
        code="D001",
        severity=DiagnosticSeverity.WARNING,
        message="Missing source field",
        source=_make_provenance(),
        event_id="evt-001",
        field="source.dataset_url",
        suggestion="Fill in dataset_url for better traceability",
    )


# ==========================================================================
# 1. Minimal AgentIRRecord
# ==========================================================================

class TestMinimalAgentIRRecord:
    """Construct a minimal AgentIRRecord with only required fields."""

    def test_valid_minimal_record(self):
        record = AgentIRRecord(
            record_id="rec-minimal-001",
            level=IRLevel.RAW,
            source=SourceRef(dataset="test-ds"),
        )
        assert record.ir_version == "0.1.0"
        assert record.record_id == "rec-minimal-001"
        assert record.level == IRLevel.RAW
        assert record.source.dataset == "test-ds"
        assert record.task is None
        assert record.tool_registry == []
        assert record.actors == []
        assert record.episodes == []
        assert record.artifacts == []
        assert record.outcome is None
        assert record.diagnostics == []
        assert record.raw == {}
        assert record.metadata == {}

    def test_omitting_record_id_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            AgentIRRecord(
                level=IRLevel.RAW,
                source=SourceRef(),  # type: ignore[call-arg]
            )
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("record_id",) for e in errors)

    def test_omitting_level_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            AgentIRRecord(
                record_id="rec-01",
                source=SourceRef(),  # type: ignore[call-arg]
            )
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("level",) for e in errors)

    def test_omitting_source_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            AgentIRRecord(
                record_id="rec-01",
                level=IRLevel.RAW,  # type: ignore[call-arg]
            )
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("source",) for e in errors)


# ==========================================================================
# 2. Full AgentIRRecord (episodes, events, tool_calls)
# ==========================================================================

class TestFullAgentIRRecord:
    """Construct a fully populated AgentIRRecord."""

    @pytest.fixture
    def full_record(self) -> AgentIRRecord:
        return AgentIRRecord(
            record_id="rec-full-001",
            level=IRLevel.CANONICAL,
            source=_make_source_ref(),
            task=_make_task_spec(),
            tool_registry=[
                _make_tool_spec("bash", "tool-01"),
                _make_tool_spec("edit", "tool-02"),
            ],
            actors=[
                _make_actor_spec("actor-01", ActorKind.ASSISTANT),
                _make_actor_spec("actor-02", ActorKind.ENVIRONMENT),
            ],
            episodes=[
                Episode(
                    episode_id="ep-001",
                    task_id="task-001",
                    attempt_id="att-001",
                    segments=[
                        Segment(
                            segment_id="seg-01",
                            kind=SegmentKind.PLAN,
                            event_ids=["evt-001"],
                        ),
                        Segment(
                            segment_id="seg-02",
                            kind=SegmentKind.ACT,
                            event_ids=["evt-002", "evt-003"],
                        ),
                    ],
                    events=[
                        _make_event("evt-001", 0, EventType.USER_MESSAGE, with_action=False),
                        _make_event("evt-002", 1, EventType.TOOL_CALL),
                        _make_event(
                            "evt-003", 2, EventType.TOOL_RESULT,
                            with_action=False, with_observation=True,
                        ),
                    ],
                    state_timeline=[
                        StateSnapshot(
                            state_id="state-01",
                            after_event_id="evt-001",
                            cwd="/workspace",
                            repo="org/repo",
                            commit="abc1234",
                        ),
                    ],
                    outcome=Outcome(
                        status=OutcomeStatus.SUCCESS,
                        reward=1.0,
                        passed=True,
                        final_answer="Fixed off-by-one error.",
                        verifier=VerifierResult(
                            type="pytest",
                            command="pytest test_binsearch.py",
                            output="1 passed in 0.45s",
                            passed=True,
                            score=1.0,
                        ),
                        metrics={"elapsed_seconds": 45.2},
                    ),
                ),
            ],
            artifacts=[
                Artifact(
                    artifact_id="artifact-01",
                    kind=ArtifactKind.PATCH,
                    path="patches/fix.diff",
                    content="@@ -42,7 +42,7 @@",
                    sha256="a" * 64,
                    size_bytes=1024,
                    created_by_event_id="evt-003",
                ),
            ],
            outcome=Outcome(
                status=OutcomeStatus.SUCCESS,
                reward=1.0,
                passed=True,
                final_answer="Task completed successfully.",
            ),
            diagnostics=[_make_diagnostic()],
            raw={"raw_trace_bytes": 655500},
            metadata={"training_run": "r123", "scenario": "testing"},
        )

    def test_full_record_structure(self, full_record):
        assert full_record.record_id == "rec-full-001"
        assert full_record.level == IRLevel.CANONICAL
        assert len(full_record.tool_registry) == 2
        assert len(full_record.actors) == 2
        assert len(full_record.episodes) == 1
        assert len(full_record.artifacts) == 1
        assert full_record.outcome is not None
        assert full_record.outcome.status == OutcomeStatus.SUCCESS
        assert len(full_record.diagnostics) == 1
        assert full_record.raw["raw_trace_bytes"] == 655500

    def test_episode_has_three_events(self, full_record):
        episode = full_record.episodes[0]
        assert len(episode.events) == 3

    def test_episode_has_two_segments(self, full_record):
        episode = full_record.episodes[0]
        assert len(episode.segments) == 2

    def test_event_actions(self, full_record):
        episode = full_record.episodes[0]
        assert episode.events[0].event_type == EventType.USER_MESSAGE
        assert episode.events[0].action is None
        assert episode.events[1].event_type == EventType.TOOL_CALL
        assert episode.events[1].action is not None
        assert episode.events[1].action.kind == ActionKind.GENERIC_TOOL
        assert episode.events[2].event_type == EventType.TOOL_RESULT
        assert episode.events[2].observation is not None
        assert episode.events[2].observation.kind == ObservationKind.TOOL_JSON


# ==========================================================================
# 3. JSON roundtrip
# ==========================================================================

class TestJSONRoundtrip:
    def test_minimal_record_roundtrip(self):
        original = AgentIRRecord(
            record_id="rec-rt-001",
            level=IRLevel.RAW,
            source=SourceRef(dataset="ds"),
        )
        json_str = original.model_dump_json()
        restored = AgentIRRecord.model_validate_json(json_str)
        assert restored.record_id == original.record_id
        assert restored.level == original.level
        assert restored.source.dataset == original.source.dataset
        assert restored.ir_version == original.ir_version

    def test_full_record_roundtrip(self):
        original = AgentIRRecord(
            record_id="rec-rt-002",
            level=IRLevel.CANONICAL,
            source=_make_source_ref(),
            task=_make_task_spec(),
            tool_registry=[_make_tool_spec("bash")],
            actors=[_make_actor_spec()],
            episodes=[
                Episode(
                    episode_id="ep-rt-001",
                    events=[_make_event("evt-rt-001", 0, EventType.TOOL_CALL)],
                ),
            ],
            artifacts=[
                Artifact(artifact_id="art-rt-001", kind=ArtifactKind.JSON),
            ],
            outcome=Outcome(status=OutcomeStatus.SUCCESS),
            raw={"key": [1, 2, {"nested": 3}]},
            metadata={"version": 2},
        )
        json_str = original.model_dump_json()
        restored = AgentIRRecord.model_validate_json(json_str)

        assert restored.record_id == "rec-rt-002"
        assert len(restored.tool_registry) == 1
        assert restored.tool_registry[0].name == "bash"
        ep = restored.episodes[0]
        assert len(ep.events) == 1
        evt = ep.events[0]
        assert evt.event_id == "evt-rt-001"
        assert evt.action is not None
        assert evt.action.tool_name == "bash"
        assert evt.action.arguments["cmd"] == "pytest tests/test_binsearch.py"
        assert evt.provenance is not None
        assert evt.provenance.dataset == "swiftbench"
        assert evt.visibility.trainable is True
        assert restored.raw == {"key": [1, 2, {"nested": 3}]}
        assert restored.outcome is not None
        assert restored.outcome.status == OutcomeStatus.SUCCESS

    def test_event_roundtrip_with_observation(self):
        original = _make_event(
            "evt-obs-01", 5, EventType.TOOL_RESULT,
            with_action=False, with_observation=True,
        )
        json_str = original.model_dump_json()
        restored = Event.model_validate_json(json_str)
        assert restored.event_id == "evt-obs-01"
        assert restored.observation is not None
        assert restored.observation.exit_code == 0
        assert len(restored.observation.content) == 1



# ==========================================================================
# 4. JSON Schema generation
# ==========================================================================

class TestJSONSchema:
    def test_schema_for_minimal_record(self):
        schema = AgentIRRecord.model_json_schema()
        assert schema["type"] == "object"
        assert "record_id" in schema["properties"]
        assert "level" in schema["properties"]
        assert "source" in schema["properties"]

        level_prop = schema["properties"]["level"]
        level_enum = level_prop.get("enum", level_prop.get("anyOf", []))

        if isinstance(level_enum, list):
            level_values = [
                item.get("const", item) if isinstance(item, dict) else item
                for item in level_enum
            ]
            flat = [v for v in level_values if isinstance(v, str)]
        else:
            flat = level_enum
        assert "raw" in flat
        assert "canonical" in flat

    def test_schema_for_event(self):
        schema = Event.model_json_schema()
        assert schema["type"] == "object"
        props = schema["properties"]
        assert "event_id" in props
        assert "event_type" in props
        assert "action" in props
        assert "observation" in props
        assert "provenance" in props
        assert "visibility" in props
        assert "state_delta" in props
        assert "control" in props

    def test_schema_for_action(self):
        schema = Action.model_json_schema()
        props = schema["properties"]
        assert "kind" in props
        assert "tool_name" in props
        assert "tool_call_id" in props
        assert "call_style" in props

    def test_schema_for_episode(self):
        schema = Episode.model_json_schema()
        props = schema["properties"]
        assert "episode_id" in props
        assert "segments" in props
        assert "events" in props
        assert "outcome" in props

    def test_schema_outcome(self):
        schema = Outcome.model_json_schema()
        props = schema["properties"]
        assert "status" in props
        assert "verifier" in props
        assert "failure_reason" in props

    def test_schema_constraints_record_id(self):
        schema = AgentIRRecord.model_json_schema()
        assert "record_id" in schema.get("required", [])





# ==========================================================================
# 5. Invalid enum values -- REJECTED
# ==========================================================================

class TestInvalidEnumValuesRejected:
    """All enum values use lowercase strings. Invalid values must fail."""

    @pytest.mark.parametrize(
        "bad_type",
        ["INVALID", "random_text", "", "ToolCall", "TOOL_CALL_UPPER", 123, None],
    )
    def test_invalid_event_type_rejected(self, bad_type):
        with pytest.raises(ValidationError):
            Event(event_id="e", idx=1, event_type=bad_type)

    def test_invalid_ir_level_rejected(self):
        with pytest.raises(ValidationError):
            AgentIRRecord(record_id="r", level="super_raw")  # type: ignore[arg-type]

    def test_invalid_content_type_rejected(self):
        with pytest.raises(ValidationError):
            ContentBlock(type="bitmap")  # type: ignore[arg-type]

    def test_invalid_message_role_rejected(self):
        with pytest.raises(ValidationError):
            Event(
                event_id="e1",
                idx=0,
                event_type=EventType.USER_MESSAGE,
                role="superuser",  # type: ignore[arg-type]
            )

    def test_invalid_action_kind_rejected(self):
        with pytest.raises(ValidationError):
            Action(kind="fly")  # type: ignore[arg-type]

    def test_invalid_call_style_rejected(self):
        with pytest.raises(ValidationError):
            Action(
                kind=ActionKind.GENERIC_TOOL,
                call_style="oral_tradition",  # type: ignore[arg-type]
            )

    def test_invalid_side_effect_level_rejected(self):
        with pytest.raises(ValidationError):
            Action(
                kind=ActionKind.MEMORY,
                side_effect_level="destroy_world",  # type: ignore[arg-type]
            )

    def test_invalid_observation_kind_rejected(self):
        with pytest.raises(ValidationError):
            Observation(kind="clairvoyance")  # type: ignore[arg-type]

    def test_invalid_segment_kind_rejected(self):
        with pytest.raises(ValidationError):
            Segment(segment_id="s1", kind="nap_time")  # type: ignore[arg-type]

    def test_invalid_actor_kind_rejected(self):
        with pytest.raises(ValidationError):
            ActorSpec(actor_id="a1", kind="alien")  # type: ignore[arg-type]

    def test_invalid_control_flow_rejected(self):
        with pytest.raises(ValidationError):
            ControlInfo(flow="chaos")  # type: ignore[arg-type]

    def test_invalid_artifact_kind_rejected(self):
        with pytest.raises(ValidationError):
            Artifact(artifact_id="a1", kind="recipe")  # type: ignore[arg-type]

    def test_invalid_outcome_status_rejected(self):
        with pytest.raises(ValidationError):
            Outcome(status="meh")  # type: ignore[arg-type]

    def test_invalid_failure_reason_rejected(self):
        with pytest.raises(ValidationError):
            Outcome(failure_reason="hungry")  # type: ignore[arg-type]

    def test_invalid_reasoning_policy_rejected(self):
        with pytest.raises(ValidationError):
            Visibility(policy="broadcast")  # type: ignore[arg-type]

    def test_invalid_redaction_status_rejected(self):
        with pytest.raises(ValidationError):
            Visibility(redaction_status="greyscale")  # type: ignore[arg-type]

    def test_invalid_diagnostic_severity_rejected(self):
        from agentir.diagnostics.diagnostic import Diagnostic
        with pytest.raises(ValidationError):
            Diagnostic(
                code="D001",
                severity="nuisance",  # type: ignore[arg-type]
                message="fail",
            )




# ==========================================================================
# 6. Extra fields allowed (ConfigDict(extra="allow"))
# ==========================================================================

class TestExtraFieldsAllowed:
    def test_extra_field_on_record(self):
        record = AgentIRRecord(
            record_id="rec-ef-001",
            level=IRLevel.RAW,
            source=SourceRef(dataset="ds"),
            my_custom_field="hello",  # type: ignore[call-arg]
        )
        assert record.my_custom_field == "hello"  # type: ignore[attr-defined]

    def test_extra_field_persists_through_roundtrip(self):
        record = AgentIRRecord(
            record_id="rec-ef-002",
            level=IRLevel.RAW,
            source=SourceRef(dataset="ds"),
            extras={"nested": {"deep": True}},  # type: ignore[call-arg]
        )
        json_str = record.model_dump_json()
        restored = AgentIRRecord.model_validate_json(json_str)
        assert restored.extras == {"nested": {"deep": True}}  # type: ignore[attr-defined]

    def test_extra_fields_on_event(self):
        evt = Event(
            event_id="evt-ef-001",
            idx=0,
            event_type=EventType.USER_MESSAGE,
            custom_tag="experimental",  # type: ignore[call-arg]
            some_dict={1: 2},  # type: ignore[call-arg]
        )
        assert evt.custom_tag == "experimental"  # type: ignore[attr-defined]
        assert evt.some_dict == {1: 2}  # type: ignore[attr-defined]



# ==========================================================================
# 7. Event with Action, Observation, ContentBlock
# ==========================================================================

class TestEventConstruction:
    def test_event_pure_user_message(self):
        cb = ContentBlock(type=ContentType.TEXT, text="Hello world")
        evt = Event(
            event_id="evt-msg-01",
            idx=0,
            event_type=EventType.USER_MESSAGE,
            actor_id="user-01",
            role=MessageRole.USER,
            content=[cb],
        )
        assert evt.event_type == EventType.USER_MESSAGE
        assert len(evt.content) == 1
        assert evt.content[0].text == "Hello world"
        assert evt.action is None
        assert evt.observation is None
        assert evt.visibility.trainable is True

    def test_event_tool_call_with_full_action(self):
        action = Action(
            kind=ActionKind.GENERIC_TOOL,
            tool_name="read_file",
            tool_call_id="call-xyz",
            arguments={"path": "/tmp/foo.py"},
            call_style=CallStyle.NATIVE_TOOL_CALL,
            side_effect_level=SideEffectLevel.READ_ONLY,
            timeout_seconds=5.0,
            metadata={"retry_count": 0},
        )
        evt = Event(
            event_id="evt-tc-01",
            idx=1,
            event_type=EventType.TOOL_CALL,
            actor_id="actor-01",
            role=MessageRole.ASSISTANT,
            action=action,
            content=[
                ContentBlock(
                    type=ContentType.JSON, json_value={"cmd": "read_file"}
                ),
            ],
        )
        assert evt.action is not None
        assert evt.action.kind == ActionKind.GENERIC_TOOL
        assert evt.action.tool_name == "read_file"
        assert evt.action.arguments["path"] == "/tmp/foo.py"
        assert evt.observation is None

    def test_event_tool_result_with_observation(self):
        observation = Observation(
            kind=ObservationKind.FILE_CONTENT,
            content=[ContentBlock(type=ContentType.TEXT, text="def foo(): pass\n")],
            exit_code=0,
            truncated=False,
            artifact_ids=["art-f-01"],
            metadata={"bytes_read": 42},
        )
        evt = Event(
            event_id="evt-tr-01",
            idx=2,
            event_type=EventType.TOOL_RESULT,
            actor_id="tool-01",
            role=MessageRole.TOOL,
            observation=observation,
            parent_event_ids=["evt-tc-01"],
        )
        assert evt.event_type == EventType.TOOL_RESULT
        assert evt.observation is not None
        assert evt.observation.kind == ObservationKind.FILE_CONTENT
        assert evt.observation.content[0].text == "def foo(): pass\n"
        assert evt.observation.exit_code == 0
        assert evt.action is None

    def test_event_with_contentblocks_mixed_types(self):
        blocks = [
            ContentBlock(type=ContentType.TEXT, text="Check this:"),
            ContentBlock(
                type=ContentType.IMAGE,
                mime_type="image/png",
                artifact_id="art-img-01",
            ),
        ]
        evt = Event(
            event_id="evt-mix-01",
            idx=0,
            event_type=EventType.ASSISTANT_MESSAGE,
            content=blocks,
        )
        assert len(evt.content) == 3
        assert evt.content[0].type == ContentType.TEXT
        assert evt.content[1].type == ContentType.JSON
        assert evt.content[2].type == ContentType.IMAGE
        assert evt.content[2].mime_type == "image/png"

