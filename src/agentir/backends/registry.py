"""Backend registry: register, get, and list available backends."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentir.backends.base import Backend

_REGISTRY: dict[str, Backend] = {}


def register_backend(backend: Backend) -> None:
    """Register a backend instance under its name."""
    _REGISTRY[backend.name] = backend


def get_backend(name: str) -> Backend:
    """Retrieve a registered backend by name.

    Raises:
        KeyError: if no backend with *name* has been registered.
    """
    if name not in _REGISTRY:
        available = ", ".join(sorted(_REGISTRY)) or "(none)"
        raise KeyError(f"Unknown backend {name!r}. Available: {available}")
    return _REGISTRY[name]


def list_backends() -> list[str]:
    """Return sorted list of registered backend names."""
    return sorted(_REGISTRY)
