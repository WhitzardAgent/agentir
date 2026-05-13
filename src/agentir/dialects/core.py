from __future__ import annotations

from agentir.dialects.registry import DialectSpec, register_dialect

register_dialect(
    DialectSpec(
        name="agent",
        event_types=[
            "system_message",
            "user_message",
            "assistant_message",
            "tool_message",
            "reasoning",
            "plan",
            "todo_update",
            "agent_handoff",
            "subtask_spawn",
            "subtask_result",
            "state_snapshot",
            "finish",
            "error",
            "unparsed_fragment",
        ],
        metadata_schema={
            "agent": {
                "phase": {
                    "type": "string",
                    "description": "Current phase of the agent execution cycle",
                },
                "confidence": {
                    "type": "number",
                    "description": "Agent confidence score for the current action or response",
                },
            },
        },
    )
)
