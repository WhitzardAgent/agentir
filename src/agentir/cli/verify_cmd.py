"""agentir verify: run verifier on AgentIR records."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from agentir.io.jsonl import read_jsonl
from agentir.ir.record import AgentIRRecord

app = typer.Typer(help="Verify AgentIR records.", rich_markup_mode="rich")


@app.command()
def verify(
    input: Annotated[Path, typer.Argument(help="Input .air.jsonl file.", show_default=False)],
    strict: Annotated[
        bool, typer.Option("--strict/--no-strict", help="Enable strict verification.")
    ] = False,
    report: Annotated[
        Path | None, typer.Option("--report", help="Write markdown diagnostic report.")
    ] = None,
) -> None:
    """Verify structural integrity of AgentIR records."""
    console = Console()
    err_console = Console(stderr=True)

    if not input.exists():
        err_console.print(f"[red]Error:[/red] Input file not found: {input}")
        raise typer.Exit(code=2)

    # Ensure passes are imported so verify pass registers
    import agentir.passes  # noqa: F401
    from agentir.diagnostics.reporter import DiagnosticReporter
    from agentir.passes.base import PassContext
    from agentir.passes.registry import get_pass

    verify_pass = get_pass("verify")
    if verify_pass is None:
        err_console.print("[red]Error:[/red] Verify pass not registered.")
        raise typer.Exit(code=3)

    ctx = PassContext(strict=strict)
    reporter = DiagnosticReporter()

    raw_records = list(read_jsonl(input))
    total = len(raw_records)

    console.print(f"Verifying {total} record(s) (strict={strict})")

    for idx, raw in enumerate(raw_records):
        record = AgentIRRecord.model_validate(raw)
        result = verify_pass.run(record, ctx)
        reporter.add_all(result.diagnostics)

    # Print results
    console.print()
    reporter.print_summary()

    if reporter.has_errors:
        console.print()
        reporter.print_diagnostics()

    # Write report if requested
    if report is not None:
        report.write_text(reporter.render_markdown())
        console.print(f"  Report written to {report}")

    console.print()
    console.print(f"Records checked: {total}")
    console.print(f"Errors: {reporter.error_count}  Warnings: {reporter.warning_count}")

    if reporter.has_errors and strict:
        raise typer.Exit(code=4)
    if reporter.has_errors:
        raise typer.Exit(code=1)
