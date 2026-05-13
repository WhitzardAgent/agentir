from agentir.dialects import browser, core, eval, file, reasoning, swe, terminal, tool
from agentir.dialects.registry import DialectSpec, get_dialect, list_dialects, register_dialect

__all__ = [
    "DialectSpec",
    "register_dialect",
    "get_dialect",
    "list_dialects",
]
