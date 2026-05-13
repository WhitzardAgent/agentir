from __future__ import annotations

from agentir.diagnostics.diagnostic import Diagnostic
from agentir.ir.base import DiagnosticSeverity


class DiagnosticCodes:
    PARSE001 = ("PARSE001", DiagnosticSeverity.WARNING, "malformed XML/tool block")
    PARSE002 = (
        "PARSE002",
        DiagnosticSeverity.WARNING,
        "diff-like text could not be parsed as unified diff",
    )
    PARSE003 = ("PARSE003", DiagnosticSeverity.WARNING, "JSON tool arguments malformed")
    PAIR001 = ("PAIR001", DiagnosticSeverity.WARNING, "tool_call has no matching tool_result")
    PAIR002 = ("PAIR002", DiagnosticSeverity.WARNING, "tool_result has no matching tool_call")
    VERIFY001 = ("VERIFY001", DiagnosticSeverity.ERROR, "duplicate event ID")
    VERIFY002 = ("VERIFY002", DiagnosticSeverity.ERROR, "invalid parent event ID")
    VERIFY003 = ("VERIFY003", DiagnosticSeverity.WARNING, "referenced artifact missing")
    VERIFY004 = ("VERIFY004", DiagnosticSeverity.WARNING, "reasoning event lacks visibility policy")
    OUTCOME001 = ("OUTCOME001", DiagnosticSeverity.WARNING, "reward/pass/status conflict")
    LOWER001 = ("LOWER001", DiagnosticSeverity.WARNING, "generated synthetic tool_call_id")
    LOWER002 = ("LOWER002", DiagnosticSeverity.WARNING, "target cannot represent artifact")
    LOWER003 = ("LOWER003", DiagnosticSeverity.WARNING, "target cannot represent reasoning event")
    LOWER004 = ("LOWER004", DiagnosticSeverity.WARNING, "structured tool call downgraded to text")
    DATA001 = ("DATA001", DiagnosticSeverity.WARNING, "empty assistant response")
    DATA002 = ("DATA002", DiagnosticSeverity.WARNING, "missing expected source field")
    SCHEMA001 = ("SCHEMA001", DiagnosticSeverity.ERROR, "Pydantic validation failed")
    IO001 = ("IO001", DiagnosticSeverity.ERROR, "input file cannot be read")
    IO002 = ("IO002", DiagnosticSeverity.ERROR, "output file cannot be written")


def make_diagnostic(
    code_tuple: tuple[str, DiagnosticSeverity, str],
    *,
    event_id: str | None = None,
    field: str | None = None,
    suggestion: str | None = None,
    source: object | None = None,
) -> Diagnostic:
    code, severity, default_msg = code_tuple
    return Diagnostic(
        code=code,
        severity=severity,
        message=default_msg,
        event_id=event_id,
        field=field,
        suggestion=suggestion,
        source=source,
    )
