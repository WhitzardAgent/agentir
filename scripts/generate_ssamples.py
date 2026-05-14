"""Generate samples/ sample trajectory files in 5 target formats.

This script creates representative sample trajectories and lowers them
into OpenAI, Anthropic, OpenHands, Hermes XML, and AgentIR Canonical formats.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from agentir.backends.base import BackendContext
from agentir.ir.action import Action
from agentir.ir.artifact import Artifact
from agentir.ir.base import (
    ActionKind,
    ArtifactKind,
    CallStyle,
    ContentType,
    EventType,
    IRLevel,
    MessageRole,
    ObservationKind,
    OutcomeStatus,
    SideEffectLevel,
)
from agentir.ir.content import ContentBlock
from agentir.ir.episode import Episode
from agentir.ir.event import Event
from agentir.ir.observation import Observation
from agentir.ir.outcome import Outcome
from agentir.ir.provenance import Provenance
from agentir.ir.record import AgentIRRecord
from agentir.ir.source import SourceRef
from agentir.ir.tool import ToolSpec
from agentir.ir.visibility import Visibility


def _text_block(text: str) -> ContentBlock:
    return ContentBlock(type=ContentType.TEXT, text=text)


def _make_event(
    event_id: str,
    idx: int,
    event_type: EventType,
    role: MessageRole | None = None,
    content: list[ContentBlock] | None = None,
    action: Action | None = None,
    observation: Observation | None = None,
) -> Event:
    return Event(
        event_id=event_id,
        idx=idx,
        event_type=event_type,
        role=role,
        content=content or [],
        action=action,
        observation=observation,
    )


def build_simple_dialogue() -> AgentIRRecord:
    """traj_01: Simple 2-turn user/assistant dialogue."""
    events = [
        _make_event(
            "evt_0000", 0, EventType.USER_MESSAGE, MessageRole.USER,
            content=[_text_block("What is the capital of France?")],
        ),
        _make_event(
            "evt_0001", 1, EventType.ASSISTANT_MESSAGE, MessageRole.ASSISTANT,
            content=[_text_block("The capital of France is Paris.")],
        ),
    ]
    return AgentIRRecord(
        record_id="traj_01",
        level=IRLevel.CANONICAL,
        source=SourceRef(dataset="example", framework="test"),
        episodes=[Episode(episode_id="ep_01", events=events)],
    )


def build_tool_use_trajectory() -> AgentIRRecord:
    """traj_02: Tool-use trajectory with multiple tool calls."""
    events = [
        _make_event(
            "evt_0000", 0, EventType.SYSTEM_MESSAGE, MessageRole.SYSTEM,
            content=[_text_block("You are a helpful assistant with access to tools.")],
        ),
        _make_event(
            "evt_0001", 1, EventType.USER_MESSAGE, MessageRole.USER,
            content=[_text_block("What is the weather in Tokyo?")],
        ),
        _make_event(
            "evt_0002", 2, EventType.TOOL_CALL, MessageRole.ASSISTANT,
            content=[_text_block("Let me check the weather for you.")],
            action=Action(
                kind=ActionKind.GENERIC_TOOL,
                tool_name="get_weather",
                tool_call_id="call_weather_1",
                arguments={"city": "Tokyo", "unit": "celsius"},
                call_style=CallStyle.NATIVE_TOOL_CALL,
                side_effect_level=SideEffectLevel.READ_ONLY,
            ),
        ),
        _make_event(
            "evt_0003", 3, EventType.TOOL_RESULT, MessageRole.TOOL,
            action=Action(
                kind=ActionKind.GENERIC_TOOL,
                tool_call_id="call_weather_1",
                call_style=CallStyle.UNKNOWN,
            ),
            observation=Observation(
                kind=ObservationKind.TOOL_JSON,
                stdout='{"temperature": 22, "condition": "partly_cloudy"}',
            ),
        ),
        _make_event(
            "evt_0004", 4, EventType.ASSISTANT_MESSAGE, MessageRole.ASSISTANT,
            content=[_text_block("The weather in Tokyo is currently partly cloudy with a temperature of 22°C.")],
        ),
    ]
    return AgentIRRecord(
        record_id="traj_02",
        level=IRLevel.CANONICAL,
        source=SourceRef(dataset="example", framework="test"),
        episodes=[Episode(episode_id="ep_02", events=events)],
        tool_registry=[
            ToolSpec(
                tool_id="tool_weather",
                name="get_weather",
                description="Get the current weather for a city",
                input_schema={
                    "type": "object",
                    "properties": {
                        "city": {"type": "string", "description": "City name"},
                        "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]},
                    },
                    "required": ["city"],
                },
            ),
        ],
    )


def build_reasoning_trajectory() -> AgentIRRecord:
    """traj_03: Reasoning-heavy trajectory with thinking."""
    events = [
        _make_event(
            "evt_0000", 0, EventType.USER_MESSAGE, MessageRole.USER,
            content=[_text_block("Prove that the square root of 2 is irrational.")],
        ),
        _make_event(
            "evt_0001", 1, EventType.REASONING, MessageRole.ASSISTANT,
            content=[_text_block("I'll use proof by contradiction. Assume sqrt(2) is rational, so sqrt(2) = p/q where p and q are coprime integers.")],
        ),
        _make_event(
            "evt_0002", 2, EventType.ASSISTANT_MESSAGE, MessageRole.ASSISTANT,
            content=[_text_block("By contradiction: assume √2 = p/q in lowest terms. Then 2 = p²/q², so p² = 2q². Thus p² is even, so p is even. Write p = 2k. Then 4k² = 2q², so q² = 2k², meaning q is also even. This contradicts p/q being in lowest terms. Therefore √2 is irrational.")],
        ),
    ]
    return AgentIRRecord(
        record_id="traj_03",
        level=IRLevel.CANONICAL,
        source=SourceRef(dataset="example", framework="test"),
        episodes=[Episode(episode_id="ep_03", events=events)],
    )


def build_coding_trajectory() -> AgentIRRecord:
    """traj_04: Coding/SWE trajectory with terminal, file ops, and git diff."""
    events = [
        _make_event(
            "evt_0000", 0, EventType.SYSTEM_MESSAGE, MessageRole.SYSTEM,
            content=[_text_block("You are a coding agent. Fix bugs in the provided repository.")],
        ),
        _make_event(
            "evt_0001", 1, EventType.USER_MESSAGE, MessageRole.USER,
            content=[_text_block("Fix the off-by-one error in the range check in utils.py")],
        ),
        _make_event(
            "evt_0002", 2, EventType.TERMINAL_COMMAND, MessageRole.ASSISTANT,
            action=Action(
                kind=ActionKind.TERMINAL,
                tool_name="terminal",
                tool_call_id="call_term_1",
                arguments={"command": "grep -n 'range' utils.py"},
                call_style=CallStyle.NATIVE_TOOL_CALL,
                side_effect_level=SideEffectLevel.READ_ONLY,
            ),
        ),
        _make_event(
            "evt_0003", 3, EventType.TERMINAL_OUTPUT, MessageRole.TOOL,
            observation=Observation(
                kind=ObservationKind.TERMINAL,
                stdout="15:    for i in range(0, len(items) - 1):\n16:        result.append(items[i])\n",
            ),
        ),
        _make_event(
            "evt_0004", 4, EventType.FILE_PATCH, MessageRole.ASSISTANT,
            action=Action(
                kind=ActionKind.FILE_PATCH,
                tool_name="file_patch",
                tool_call_id="call_patch_1",
                arguments={"path": "utils.py"},
                call_style=CallStyle.NATIVE_TOOL_CALL,
                side_effect_level=SideEffectLevel.WORKSPACE_WRITE,
            ),
            content=[ContentBlock(type=ContentType.DIFF, text="diff --git a/utils.py b/utils.py\n--- a/utils.py\n+++ b/utils.py\n@@ -12,7 +12,7 @@\n-    for i in range(0, len(items) - 1):\n+    for i in range(0, len(items)):\n         result.append(items[i])\n")],
        ),
        _make_event(
            "evt_0005", 5, EventType.TERMINAL_COMMAND, MessageRole.ASSISTANT,
            action=Action(
                kind=ActionKind.TERMINAL,
                tool_name="terminal",
                tool_call_id="call_term_2",
                arguments={"command": "python -m pytest tests/test_utils.py -v"},
                call_style=CallStyle.NATIVE_TOOL_CALL,
                side_effect_level=SideEffectLevel.READ_ONLY,
            ),
        ),
        _make_event(
            "evt_0006", 6, EventType.TERMINAL_OUTPUT, MessageRole.TOOL,
            observation=Observation(
                kind=ObservationKind.TERMINAL,
                stdout="test_range_check ... ok\n1 passed in 0.02s\n",
            ),
        ),
        _make_event(
            "evt_0007", 7, EventType.ASSISTANT_MESSAGE, MessageRole.ASSISTANT,
            content=[_text_block("I fixed the off-by-one error in utils.py by changing `range(0, len(items) - 1)` to `range(0, len(items))`. All tests pass.")],
        ),
    ]
    diff_text = "diff --git a/utils.py b/utils.py\n--- a/utils.py\n+++ b/utils.py\n@@ -12,7 +12,7 @@\n-    for i in range(0, len(items) - 1):\n+    for i in range(0, len(items)):\n         result.append(items[i])\n"
    return AgentIRRecord(
        record_id="traj_04",
        level=IRLevel.CANONICAL,
        source=SourceRef(dataset="example", framework="test"),
        episodes=[Episode(episode_id="ep_04", events=events)],
        artifacts=[
            Artifact(
                artifact_id="patch_01",
                kind=ArtifactKind.PATCH,
                content=diff_text,
                mime_type="text/x-diff",
            )
        ],
        outcome=Outcome(status=OutcomeStatus.SUCCESS, passed=True),
    )


def main() -> None:
    import agentir.backends  # noqa: F401
    from agentir.backends.anthropic_tools import AnthropicToolsBackend
    from agentir.backends.hermes_xml import HermesXMLBackend
    from agentir.backends.openai_tools import OpenAIToolsBackend
    from agentir.backends.openhands import OpenHandsBackend
    from agentir.backends.sharegpt import ShareGPTBackend

    base_dir = Path(__file__).resolve().parent.parent / "samples"
    base_dir.mkdir(exist_ok=True)

    records = [
        build_simple_dialogue(),
        build_tool_use_trajectory(),
        build_reasoning_trajectory(),
        build_coding_trajectory(),
    ]

    ctx_no_reasoning = BackendContext(
        reasoning_policy="metadata_only",
        include_reasoning=False,
        tool_policy="structured",
    )
    ctx_with_reasoning = BackendContext(
        reasoning_policy="preserve",
        include_reasoning=True,
        tool_policy="structured",
    )

    backends = [
        ("openai", OpenAIToolsBackend(), ctx_no_reasoning),
        ("anthropic", AnthropicToolsBackend(), ctx_no_reasoning),
        ("openhands", OpenHandsBackend(), ctx_no_reasoning),
        ("hermes", HermesXMLBackend(), ctx_with_reasoning),
    ]

    for record in records:
        rid = record.record_id

        # AgentIR Canonical (just serialize the record)
        canonical_path = base_dir / f"{rid}.agentir.json"
        canonical_data = record.model_dump(mode="json", exclude_none=True)
        canonical_path.write_text(json.dumps(canonical_data, indent=2, ensure_ascii=False) + "\n")
        print(f"  wrote {canonical_path}")

        # Other formats
        for fmt_name, backend, ctx in backends:
            result = backend.lower_record(record, ctx)
            if fmt_name == "hermes":
                out_path = base_dir / f"{rid}.hermes.xml"
            else:
                out_path = base_dir / f"{rid}.{fmt_name}.json"

            out_path.write_text(json.dumps(result.output, indent=2, ensure_ascii=False) + "\n")
            print(f"  wrote {out_path} (status={result.report.status.value})")


if __name__ == "__main__":
    main()
