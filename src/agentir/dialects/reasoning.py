from __future__ import annotations

from agentir.dialects.registry import DialectSpec, register_dialect

register_dialect(
    DialectSpec(
        name="reasoning",
        event_types=["reasoning", "plan"],
        metadata_schema={
            "visibility": {
                "contains_reasoning": {
                    "type": "boolean",
                    "description": "Whether the event contains reasoning content visible to the user or downstream consumer",
                },
                "trainable": {
                    "type": "boolean",
                    "description": "Whether the reasoning content is included in the training signal",
                },
                "policy": {
                    "type": "string",
                    "description": "Visibility policy applied to the reasoning content, e.g. always, never, truncated",
                },
            },
        },
    )
)
