from __future__ import annotations

from agentir.passes.base import AgentIRPass

_registry: dict[str, AgentIRPass] = {}


def register_pass(pass_instance: AgentIRPass) -> None:
    _registry[pass_instance.name] = pass_instance


def get_pass(name: str) -> AgentIRPass | None:
    return _registry.get(name)


def list_passes() -> list[str]:
    return list(_registry.keys())
