"""AgentIR Format DSL -- declarative trajectory format definitions."""

from agentir.dsl.models import TrajectoryFormat, SourceDef, DetectDef, DetectRule, EmitSpec, EventMapping, EpisodeMapping
from agentir.dsl.loader import load_dsl, validate_dsl
from agentir.dsl.compiler import compile_dsl_frontend, RuntimeDSLFrontend

__all__ = [
    "TrajectoryFormat",
    "SourceDef",
    "DetectDef",
    "DetectRule",
    "EmitSpec",
    "EventMapping",
    "EpisodeMapping",
    "load_dsl",
    "validate_dsl",
    "compile_dsl_frontend",
    "RuntimeDSLFrontend",
]
