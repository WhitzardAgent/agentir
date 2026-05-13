from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, Field

from agentir.diagnostics.diagnostic import Diagnostic
from agentir.ir.record import AgentIRRecord


class FrontendContext(BaseModel):
    dataset: str | None = None
    dataset_url: str | None = None
    config: str | None = None
    split: str | None = None
    row_index: int | None = None
    strict: bool = False


class FrontendResult(BaseModel):
    record: AgentIRRecord | None = None
    diagnostics: list[Diagnostic] = Field(default_factory=list)


class BaseFrontend(ABC):
    name: str

    @abstractmethod
    def detect(self, sample: Mapping[str, Any]) -> float: ...

    @abstractmethod
    def parse_record(self, sample: Mapping[str, Any], ctx: FrontendContext) -> FrontendResult: ...
