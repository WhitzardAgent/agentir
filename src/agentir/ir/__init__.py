"""AgentIR intermediate representation models.

This package uses lazy imports to avoid circular dependency issues
between ir.record -> diagnostics.diagnostic -> ir.base / ir.provenance.
"""

from agentir.ir.base import (
    ActionKind,
    ActorKind,
    ArtifactKind,
    CallStyle,
    ContentType,
    ControlFlow,
    DiagnosticSeverity,
    EventType,
    FailureReason,
    IRLevel,
    LoweringStatus,
    MessageRole,
    ObservationKind,
    OutcomeStatus,
    PassKind,
    ReasoningPolicy,
    RedactionStatus,
    SegmentKind,
    SideEffectLevel,
)

# Lazy imports for models that have cross-package dependencies.
# Accessing these names triggers the import on first use.


def __getattr__(name: str):
    _lazy = {
        "Action": "agentir.ir.action",
        "ActorSpec": "agentir.ir.actor",
        "Artifact": "agentir.ir.artifact",
        "ContentBlock": "agentir.ir.content",
        "ControlInfo": "agentir.ir.control",
        "Episode": "agentir.ir.episode",
        "Segment": "agentir.ir.episode",
        "Event": "agentir.ir.event",
        "Observation": "agentir.ir.observation",
        "Outcome": "agentir.ir.outcome",
        "VerifierResult": "agentir.ir.outcome",
        "Provenance": "agentir.ir.provenance",
        "AgentIRRecord": "agentir.ir.record",
        "SourceRef": "agentir.ir.source",
        "StateDelta": "agentir.ir.state",
        "StateSnapshot": "agentir.ir.state",
        "TaskSpec": "agentir.ir.task",
        "EnvironmentSpec": "agentir.ir.task",
        "ToolSpec": "agentir.ir.tool",
        "Visibility": "agentir.ir.visibility",
    }
    if name in _lazy:
        import importlib

        mod = importlib.import_module(_lazy[name])
        return getattr(mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Enums
    "ActionKind",
    "ActorKind",
    "ArtifactKind",
    "CallStyle",
    "ContentType",
    "ControlFlow",
    "DiagnosticSeverity",
    "EventType",
    "FailureReason",
    "IRLevel",
    "LoweringStatus",
    "MessageRole",
    "ObservationKind",
    "OutcomeStatus",
    "PassKind",
    "ReasoningPolicy",
    "RedactionStatus",
    "SegmentKind",
    "SideEffectLevel",
    # Models (lazy)
    "Action",
    "ActorSpec",
    "AgentIRRecord",
    "Artifact",
    "ContentBlock",
    "ControlInfo",
    "EnvironmentSpec",
    "Episode",
    "Event",
    "Observation",
    "Outcome",
    "Provenance",
    "Segment",
    "SourceRef",
    "StateDelta",
    "StateSnapshot",
    "TaskSpec",
    "ToolSpec",
    "VerifierResult",
    "Visibility",
]
