from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from agentir.diagnostics.diagnostic import Diagnostic
from agentir.ir.base import PassKind
from agentir.ir.record import AgentIRRecord


class PassContext(BaseModel):
    strict: bool = False
    reasoning_policy: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)


class PassResult(BaseModel):
    record: AgentIRRecord
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    analysis: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)


class AgentIRPass(ABC):
    name: str
    kind: PassKind

    @abstractmethod
    def run(self, record: AgentIRRecord, ctx: PassContext) -> PassResult: ...
