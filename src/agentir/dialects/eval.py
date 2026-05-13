from __future__ import annotations

from agentir.dialects.registry import DialectSpec, register_dialect

register_dialect(
    DialectSpec(
        name="eval",
        event_types=["verification", "reward"],
        metadata_schema={
            "eval": {
                "verifier": {
                    "type": {
                        "type": "string",
                        "description": "Type of verifier used, e.g. unit_test, human, llm_judge",
                    },
                },
                "passed": {
                    "type": "boolean",
                    "description": "Whether the verification passed",
                },
                "reward": {
                    "type": "number",
                    "description": "Numeric reward signal from evaluation",
                },
                "failure_reason": {
                    "type": "string",
                    "description": "Reason for verification failure, if applicable",
                },
            },
        },
    )
)
