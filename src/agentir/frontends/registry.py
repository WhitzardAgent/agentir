from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from agentir.frontends.base import BaseFrontend

_registry: dict[str, BaseFrontend] = {}


def register_frontend(frontend: BaseFrontend) -> None:
    _registry[frontend.name] = frontend


def get_frontend(name: str) -> BaseFrontend | None:
    return _registry.get(name)


def list_frontends() -> list[str]:
    return list(_registry.keys())


def detect_frontend(sample: Mapping[str, Any]) -> list[tuple[str, float]]:
    scores: list[tuple[str, float]] = []
    for name, frontend in _registry.items():
        try:
            score = frontend.detect(sample)
        except Exception:
            score = 0.0
        scores.append((name, score))
    scores.sort(key=lambda x: x[1], reverse=True)
    return scores
