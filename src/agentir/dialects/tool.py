from __future__ import annotations

from agentir.dialects.registry import DialectSpec, register_dialect

register_dialect(
    DialectSpec(
        name="tool",
        event_types=["tool_call", "tool_result"],
        metadata_schema={
            "tool": {
                "name": {
                    "raw": {
                        "type": "string",
                        "description": "Raw tool name as it appears in the trace",
                    },
                    "normalized": {
                        "type": "string",
                        "description": "Canonical / normalized tool name",
                    },
                },
                "call_style": {
                    "type": "string",
                    "description": "Invocation style of the tool call, e.g. function_call, json, xml",
                },
                "call_id": {
                    "type": "string",
                    "description": "Unique identifier linking a tool_call to its tool_result",
                },
                "schema": {
                    "available": {
                        "type": "boolean",
                        "description": "Whether the tool schema was available at call time",
                    },
                },
            },
        },
    )
)
