"""agentir-opt: pass pipeline command (IR -> IR)."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn

from agentir.io.jsonl import read_jsonl, write_jsonl
from agentir.io.parquet import write_parquet
from agentir.ir.record import AgentIRRecord


def _ensure_passes_registered() -> None:
    """Import all pass modules so they self-register."""
    import importlib

    _pass_modules = [
        "agentir.passes.canonicalize_tools",
        "agentir.passes.extract_patches",
        "agentir.passes.normalize_outcome",
        "agentir.passes.pair_tool_results",
        "agentir.passes.parse_claude_log",
        "agentir.passes.parse_hermes_xml",
        "agentir.passes.parse_openhands_tool_calls",
        "agentir.passes.parse_sharegpt",
        "agentir.passes.redact_reasoning",
        "agentir.passes.slice_training",
        "agentir.passes.verify",
    ]
    for mod_name in _pass_modules:
        try:
            importlib.import_module(mod_name)
        except Exception:
            pass


app = typer.Typer(
    name="agentir-opt",
    help="Run a pass pipeline over AgentIR records.",
    no_args_is_help=True,
    rich_markup_mode="rich",
    add_completion=False,
)

err_console = Console(stderr=True)


def _infer_format(output: Path, fmt: str | None) -> str:
    if fmt is not None:
        return fmt
    suffix = output.suffix.lower()
    if suffix == ".parquet":
        return "parquet"
    return "jsonl"


def _record_to_dict(record: AgentIRRecord) -> dict:
    """Serialize an AgentIRRecord to a dict, filtering None values."""
    data = record.model_dump(mode="json")
    return {k: v for k, v in data.items() if v is not None}


@app.command()
def main(
    input: Annotated[Path, typer.Argument(help="Input .air.jsonl file.", show_default=False)],
    passes: Annotated[
        str, typer.Option("--passes", help="Comma-separated pass names.", show_default=False)
    ],
    output: Annotated[
        Path, typer.Option("--output", help="Output file path.", show_default=False)
    ] = ...,
    reasoning_policy: Annotated[
        str | None,
        typer.Option("--reasoning-policy", help="preserve|summarize|drop|redact|metadata_only"),
    ] = None,
    strict: Annotated[
        bool, typer.Option("--strict/--no-strict", help="Strict verifier behavior.")
    ] = False,
    report: Annotated[
        Path | None, typer.Option("--report", help="Write markdown diagnostic report.")
    ] = None,
    format: Annotated[
        str | None, typer.Option("--format", help="Output format: jsonl|parquet.")
    ] = None,
) -> None:
    """Run a pass pipeline over AgentIR records."""
    console = Console()

    if not input.exists():
        err_console.print(f"[red]Error:[/red] Input file not found: {input}")
        raise typer.Exit(code=2)

    fmt = _infer_format(output, format)
    pass_names = [p.strip() for p in passes.split(",") if p.strip()]

    if not pass_names:
        err_console.print("[red]Error:[/red] No passes specified.")
        raise typer.Exit(code=2)

    # Ensure passes are imported so they register
    _ensure_passes_registered()

    from agentir.diagnostics.reporter import DiagnosticReporter
    from agentir.passes.base import PassContext
    from agentir.passes.manager import PassManager
    from agentir.passes.registry import get_pass, list_passes

    # Validate pass names
    for name in pass_names:
        if get_pass(name) is None:
            available = ", ".join(list_passes()) or "(none)"
            err_console.print(f"[red]Error:[/red] Unknown pass '{name}'. Available: {available}")
            raise typer.Exit(code=3)

    ctx = PassContext(strict=strict, reasoning_policy=reasoning_policy)
    manager = PassManager()
    reporter = DiagnosticReporter()

    records_out: list[dict] = []
    total_processed = 0

    # Read input records
    raw_records = list(read_jsonl(input))
    total = len(raw_records)

    console.print(f"Running [bold]{len(pass_names)}[/bold] pass(es) on {total} record(s)")
    console.print(f"  Passes: [cyan]{', '.join(pass_names)}[/cyan]")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Processing...", total=total)

        for raw in raw_records:
            record = AgentIRRecord.model_validate(raw)

            try:
                result = manager.run_pipeline(record, pass_names, ctx)
            except ValueError as exc:
                err_console.print(f"[red]Error:[/red] {exc}")
                raise typer.Exit(code=3)

            reporter.add_all(result.diagnostics)
            records_out.append(_record_to_dict(result.record))
            total_processed += 1
            progress.advance(task)

    # Write output
    if fmt == "parquet":
        count = write_parquet(output, records_out)
    else:
        count = write_jsonl(output, iter(records_out))

    console.print()
    console.print(f"[bold green]Done.[/bold green] Wrote {count} records to {output}")

    if reporter.has_errors:
        reporter.print_summary()
        if strict:
            raise typer.Exit(code=1)

    # Write markdown report if requested
    if report is not None:
        report.write_text(reporter.render_markdown())
        console.print(f"  Diagnostic report written to {report}")

    if reporter.has_errors:
        raise typer.Exit(code=1)
