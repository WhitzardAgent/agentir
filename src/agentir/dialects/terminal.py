from __future__ import annotations

from agentir.dialects.registry import DialectSpec, register_dialect

register_dialect(
    DialectSpec(
        name="terminal",
        event_types=["terminal_command", "terminal_output"],
        metadata_schema={
            "action": {
                "kind": {
                    "type": "string",
                    "description": "Kind of terminal action, e.g. command, script, interactive",
                },
                "side_effect_level": {
                    "type": "string",
                    "description": "Severity of side effects, e.g. none, read_only, mutating, destructive",
                },
            },
        },
    )
)
