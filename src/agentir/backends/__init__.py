"""Backend lowering subsystem for AgentIR.

Importing this package registers all built-in backends.
"""

# Import backends to trigger registration
from agentir.backends import (
    hermes_xml,  # noqa: F401
    openai_tools,  # noqa: F401
    openhands,  # noqa: F401
    process_supervision,  # noqa: F401
    sft,  # noqa: F401
    sharegpt,  # noqa: F401
)
from agentir.backends.base import Backend, BackendContext
from agentir.backends.loss import LossItem, LossReport, LoweringResult
from agentir.backends.registry import get_backend, list_backends, register_backend

__all__ = [
    "Backend",
    "BackendContext",
    "LossItem",
    "LossReport",
    "LoweringResult",
    "get_backend",
    "list_backends",
    "register_backend",
]
