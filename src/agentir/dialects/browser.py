from __future__ import annotations

from agentir.dialects.registry import DialectSpec, register_dialect

register_dialect(
    DialectSpec(
        name="browser",
        event_types=["browser_action", "browser_observation"],
        artifact_kinds=["screenshot", "webpage"],
    )
)
