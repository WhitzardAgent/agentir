"""Visibility and redaction models."""

from __future__ import annotations

from pydantic import BaseModel

from agentir.ir.base import ReasoningPolicy, RedactionStatus


class Visibility(BaseModel):
    """Visibility and training suitability flags."""

    trainable: bool = True
    contains_reasoning: bool = False
    contains_sensitive: bool = False
    redaction_status: RedactionStatus = RedactionStatus.NONE
    policy: ReasoningPolicy | None = None
