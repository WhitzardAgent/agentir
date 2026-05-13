"""DSL loader: read, validate, and parse ``*.agentir.yaml`` files."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from yaml import YAMLError

from agentir.diagnostics.diagnostic import Diagnostic
from agentir.dsl.models import TrajectoryFormat
from agentir.ir.base import DiagnosticSeverity


def _read_yaml(path: str | Path) -> dict[str, Any]:
    """Read a YAML file and return parsed dict.

    Args:
        path: Path to the YAML file.

    Returns:
        Parsed dictionary from the YAML file.

    Raises:
        FileNotFoundError: if the file does not exist.
        ValueError: if the YAML document is empty, null, or not a mapping.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"DSL file not found: {path}")
    with open(p, "r", encoding="utf-8") as f:
        try:
            data = yaml.safe_load(f)
        except YAMLError as e:
            raise ValueError(f"YAML parse error in {path}: {e}")
    if data is None:
        raise ValueError(f"Empty or null YAML document: {path}")
    if not isinstance(data, dict):
        raise ValueError(
            f"YAML root must be a mapping (dict), got {type(data).__name__}: {path}"
        )
    return data


def load_dsl(path: str | Path) -> TrajectoryFormat:
    """Load and parse a ``*.agentir.yaml`` DSL file into a validated model.

    Args:
        path: Path to the ``.agentir.yaml`` file.

    Returns:
        A validated :class:`TrajectoryFormat` instance.

    Raises:
        FileNotFoundError: if *path* does not exist.
        ValueError: if YAML parsing fails or the document is not valid DSL.
    """
    raw = _read_yaml(path)
    return TrajectoryFormat.model_validate(raw)


def validate_dsl(path: str | Path) -> tuple[bool, list[Diagnostic]]:
    """Validate a DSL file and return diagnostics.

    Checks required top-level fields, apiVersion compatibility, episode
    presence, and performs full Pydantic validation.

    Args:
        path: Path to the ``.agentir.yaml`` file.

    Returns:
        ``(valid, diagnostics)``.  If *valid* is ``True`` the DSL is
        well-formed and validates against the schema.
    """
    diagnostics: list[Diagnostic] = []

    # --- Read YAML -----------------------------------------------------------
    try:
        raw = _read_yaml(path)
    except FileNotFoundError as e:
        diagnostics.append(
            Diagnostic(
                code="IO001",
                severity=DiagnosticSeverity.ERROR,
                message=str(e),
            )
        )
        return False, diagnostics
    except ValueError as e:
        diagnostics.append(
            Diagnostic(
                code="PARSE003",
                severity=DiagnosticSeverity.ERROR,
                message=str(e),
            )
        )
        return False, diagnostics

    # --- Check required top-level fields -------------------------------------
    # These checks run before Pydantic validation has better error messages.
    required_fields = {"apiVersion", "kind", "metadata", "source"}
    missing = required_fields - set(raw.keys())
    if missing:
        diagnostics.append(
            Diagnostic(
                code="SCHEMA001",
                severity=DiagnosticSeverity.ERROR,
                message=f"Missing required fields: {', '.join(sorted(missing))}",
            )
        )

    # --- Check apiVersion compatibility --------------------------------------
    api_version = raw.get("apiVersion")
    if api_version and api_version != "agentir.qitor.ai/v0.1":
        diagnostics.append(
            Diagnostic(
                code="SCHEMA003",
                severity=DiagnosticSeverity.WARNING,
                message=(
                    f"Unknown DSL apiVersion: {api_version}. "
                    f"Expected agentir.qitor.ai/v0.1"
                ),
            )
        )

    # --- Check episodes ------------------------------------------------------
    episodes = raw.get("episodes", [])
    if not episodes:
        diagnostics.append(
            Diagnostic(
                code="SCHEMA002",
                severity=DiagnosticSeverity.ERROR,
                message="At least one episode with event mappings is required",
            )
        )

    # --- Try full Pydantic validation ----------------------------------------
    try:
        TrajectoryFormat.model_validate(raw)
        valid = (
            len([d for d in diagnostics if d.severity == DiagnosticSeverity.ERROR])
            == 0
        )
        return valid, diagnostics
    except Exception as e:
        diagnostics.append(
            Diagnostic(
                code="PARSE003",
                severity=DiagnosticSeverity.ERROR,
                message=f"DSL validation failed: {e}",
            )
        )
        return False, diagnostics
