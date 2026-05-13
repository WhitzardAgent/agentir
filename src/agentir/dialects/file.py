from __future__ import annotations

from agentir.dialects.registry import DialectSpec, register_dialect

register_dialect(
    DialectSpec(
        name="file",
        event_types=["file_read", "file_write", "file_patch"],
        artifact_kinds=["patch", "file"],
    )
)
