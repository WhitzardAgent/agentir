"""Outcome and verification models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from agentir.ir.base import FailureReason, OutcomeStatus


class VerifierResult(BaseModel):
    """Result from a verifier check."""

    type: str | None = None
    command: str | None = None
    output: str | None = None
    passed: bool | None = None
    score: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Outcome(BaseModel):
    """Outcome of an episode or task attempt."""

    status: OutcomeStatus = OutcomeStatus.UNKNOWN
    reward: float | None = None
    passed: bool | None = None
    verifier: VerifierResult | None = None
    final_answer: str | None = None
    final_patch_artifact_id: str | None = None
    failure_reason: FailureReason | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
