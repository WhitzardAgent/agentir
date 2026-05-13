from __future__ import annotations

from typing import TextIO

from rich.console import Console
from rich.table import Table

from agentir.diagnostics.diagnostic import Diagnostic
from agentir.ir.base import DiagnosticSeverity


def format_diagnostic(d: Diagnostic) -> str:
    parts = [f"{d.severity.value}[{d.code}]: {d.message}"]
    if d.source:
        src = d.source
        loc_parts = []
        if src.dataset:
            loc_parts.append(src.dataset)
        if src.split:
            loc_parts.append(src.split)
        if src.row_id is not None:
            loc_parts.append(f"row {src.row_id}")
        elif src.row_index is not None:
            loc_parts.append(f"row {src.row_index}")
        if src.source_field:
            loc_parts.append(src.source_field)
        if loc_parts:
            parts.append(f"  --> {':'.join(loc_parts)}")
    if d.event_id:
        parts.append(f"  event: {d.event_id}")
    if d.field:
        parts.append(f"  field: {d.field}")
    if d.suggestion:
        parts.append(f"  help: {d.suggestion}")
    return "\n".join(parts)


class DiagnosticReporter:
    def __init__(self, file: TextIO | None = None) -> None:
        self.console = Console(file=file) if file else Console()
        self.diagnostics: list[Diagnostic] = []
        self._counts: dict[DiagnosticSeverity, int] = {
            DiagnosticSeverity.INFO: 0,
            DiagnosticSeverity.WARNING: 0,
            DiagnosticSeverity.ERROR: 0,
            DiagnosticSeverity.FATAL: 0,
        }

    def add(self, d: Diagnostic) -> None:
        self.diagnostics.append(d)
        self._counts[d.severity] += 1

    def add_all(self, diagnostics: list[Diagnostic]) -> None:
        for d in diagnostics:
            self.add(d)

    @property
    def has_errors(self) -> bool:
        return (
            self._counts[DiagnosticSeverity.ERROR] > 0 or self._counts[DiagnosticSeverity.FATAL] > 0
        )

    @property
    def error_count(self) -> int:
        return self._counts[DiagnosticSeverity.ERROR] + self._counts[DiagnosticSeverity.FATAL]

    @property
    def warning_count(self) -> int:
        return self._counts[DiagnosticSeverity.WARNING]

    def print_summary(self) -> None:
        table = Table(title="Diagnostic Summary")
        table.add_column("Severity", style="bold")
        table.add_column("Count", justify="right")
        for sev in DiagnosticSeverity:
            count = self._counts[sev]
            if count > 0:
                style = (
                    "red"
                    if sev in (DiagnosticSeverity.ERROR, DiagnosticSeverity.FATAL)
                    else "yellow"
                    if sev == DiagnosticSeverity.WARNING
                    else None
                )
                table.add_row(sev.value, str(count), style=style)
        self.console.print(table)

    def print_diagnostics(self) -> None:
        for d in self.diagnostics:
            self.console.print(format_diagnostic(d))

    def render_markdown(self) -> str:
        lines = ["# Diagnostics Report", ""]
        lines.append("## Summary")
        lines.append("")
        for sev in DiagnosticSeverity:
            count = self._counts[sev]
            lines.append(f"- {sev.value}: {count}")
        lines.append("")
        if self.diagnostics:
            lines.append("## Details")
            lines.append("")
            for d in self.diagnostics:
                lines.append(f"### {d.severity.value}[{d.code}]")
                lines.append(f"- Message: {d.message}")
                if d.event_id:
                    lines.append(f"- Event: {d.event_id}")
                if d.field:
                    lines.append(f"- Field: {d.field}")
                if d.suggestion:
                    lines.append(f"- Suggestion: {d.suggestion}")
                lines.append("")
        return "\n".join(lines)
