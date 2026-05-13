from __future__ import annotations

from collections.abc import Mapping
from typing import Any

ROLE_MAP = {
    "human": "user",
    "user": "user",
    "gpt": "assistant",
    "assistant": "assistant",
    "system": "system",
    "tool": "tool",
    "developer": "developer",
}


def normalize_role(raw_role: str) -> str:
    return ROLE_MAP.get(raw_role.lower().strip(), "unknown")


def get_conversation_text(turn: Mapping[str, Any]) -> str:
    for key in ("value", "content", "text"):
        val = turn.get(key)
        if isinstance(val, str):
            return val
    if isinstance(turn.get("content"), list):
        parts = []
        for block in turn["content"]:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
        return "\n".join(parts)
    return ""


def get_conversation_role(turn: Mapping[str, Any]) -> str:
    for key in ("from", "role", "speaker"):
        val = turn.get(key)
        if isinstance(val, str):
            return normalize_role(val)
    return "unknown"
