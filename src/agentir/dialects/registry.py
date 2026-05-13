from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DialectSpec(BaseModel):
    name: str
    version: str = "0.1.0"
    event_types: list[str] = Field(default_factory=list)
    artifact_kinds: list[str] = Field(default_factory=list)
    metadata_schema: dict[str, Any] = Field(default_factory=dict)


_registry: dict[str, DialectSpec] = {}


def register_dialect(spec: DialectSpec) -> None:
    _registry[spec.name] = spec


def get_dialect(name: str) -> DialectSpec | None:
    return _registry.get(name)


def list_dialects() -> list[str]:
    return list(_registry.keys())
