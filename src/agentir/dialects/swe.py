from __future__ import annotations

from agentir.dialects.registry import DialectSpec, register_dialect

register_dialect(
    DialectSpec(
        name="swe",
        event_types=["file_patch", "verification", "reward"],
        metadata_schema={
            "swe": {
                "repo": {
                    "type": "string",
                    "description": "Repository URL or identifier",
                },
                "base_commit": {
                    "type": "string",
                    "description": "The base commit hash the patch is applied against",
                },
                "issue_id": {
                    "type": "string",
                    "description": "Identifier for the issue being resolved",
                },
                "benchmark": {
                    "type": "string",
                    "description": "Benchmark name, e.g. SWE-bench, SWE-bench-lite",
                },
                "dataset": {
                    "type": "string",
                    "description": "Dataset name or split the instance belongs to",
                },
            },
        },
    )
)
