from __future__ import annotations

from pydantic import BaseModel, Field

from agentir.ir.provenance import Provenance


class SourceMapEntry(BaseModel):
    event_id: str
    provenance: Provenance


class SourceMap(BaseModel):
    record_id: str
    entries: list[SourceMapEntry] = Field(default_factory=list)

    def add(self, event_id: str, provenance: Provenance) -> None:
        self.entries.append(SourceMapEntry(event_id=event_id, provenance=provenance))

    def lookup(self, event_id: str) -> Provenance | None:
        for entry in self.entries:
            if entry.event_id == event_id:
                return entry.provenance
        return None
