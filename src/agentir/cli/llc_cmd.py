"""agentir-llc: lowering backend command (IR -> target format)."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn
from rich.table import Table

from agentir.io.jsonl import read_jsonl, write_jsonl
from agentir.io.parquet import write_parquet
from agentir.ir.record import AgentIRRecord

app = typer.Typer(
    name="agentir-llc",
    help="Lower AgentIR records into a target training format.",
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


@app.command()
def main(
    input: Annotated[Path, typer.Argument(help="Input .air.jsonl file.", show_default=False)],
    target: Annotated[
        str,
        typer.Option(
            "--target",
            help="Target format: sft|process-supervision|openai-tools|hermes-xml|openhands|sharegpt.",
            show_default=False,
        ),
    ] = ...,
    output: Annotated[
        Path, typer.Option("--output", help="Output file path.", show_default=False)
    ] = ...,
    loss_report: Annotated[
        Path | None, typer.Option("--loss-report", help="Write loss report as markdown.")
    ] = None,
    reasoning_policy: Annotated[
        str | None,
        typer.Option("--reasoning-policy", help="preserve|summarize|drop|redact|metadata_only"),
    ] = "metadata_only",
    include_reasoning: Annotated[
        bool,
        typer.Option(
            "--include-reasoning/--no-include-reasoning", help="Include reasoning in output."
        ),
    ] = False,
    tool_policy: Annotated[
        str, typer.Option("--tool-policy", help="structured|inline|drop")
    ] = "structured",
    format: Annotated[
        str | None, typer.Option("--format", help="Output format: jsonl|parquet.")
    ] = None,
) -> None:
    """Lower AgentIR records into a target training format."""
    console = Console()

    if not input.exists():
        err_console.print(f"[red]Error:[/red] Input file not found: {input}")
        raise typer.Exit(code=2)

    fmt = _infer_format(output, format)

    # Ensure backends are imported so they register
    import agentir.backends  # noqa: F401
    from agentir.backends.base import BackendContext
    from agentir.backends.registry import get_backend, list_backends

    # Resolve backend
    try:
        backend = get_backend(target)
    except KeyError as exc:
        available = ", ".join(list_backends()) or "(none)"
        err_console.print(f"[red]Error:[/red] {exc}. Available: {available}")
        raise typer.Exit(code=3)

    ctx = BackendContext(
        reasoning_policy=reasoning_policy,
        include_reasoning=include_reasoning,
        tool_policy=tool_policy,
    )

    total_by_status: dict[str, int] = {}
    total_losses = 0

    # Read input records
    raw_records = list(read_jsonl(input))
    total = len(raw_records)

    console.print(f"Lowering {total} record(s) to [bold]{target}[/bold] format")

    outputs: list[dict] = []
    loss_reports: list = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Lowering...", total=total)

        for raw in raw_records:
            record = AgentIRRecord.model_validate(raw)

            result = backend.lower_record(record, ctx)
            outputs.append(result.output)
            loss_reports.append(result.report)

            # Track status
            status_str = result.report.status.value
            total_by_status[status_str] = total_by_status.get(status_str, 0) + 1
            total_losses += len(result.report.losses)

            progress.advance(task)

    # Write output
    if fmt == "parquet":
        count = write_parquet(output, outputs)
    else:
        count = write_jsonl(output, iter(outputs))

    # Summary table
    console.print()
    console.print(f"[bold green]Done.[/bold green] Wrote {count} records to {output}")

    if total_by_status:
        table = Table(title="Lowering Summary")
        table.add_column("Status", style="bold")
        table.add_column("Count", justify="right")
        for status, cnt in sorted(total_by_status.items()):
            style = "green" if status == "exact" else "yellow" if status == "lossy" else "red"
            table.add_row(status, str(cnt), style=style)
        console.print(table)

    if total_losses:
        console.print(f"  Total loss items: {total_losses}")

    # Write loss report if requested
    if loss_report is not None:
        lines = ["# Loss Report", ""]
        lines.append("## Summary")
        lines.append("")
        lines.append(f"- Total records: {total}")
        lines.append(f"- Total loss items: {total_losses}")
        for status, cnt in sorted(total_by_status.items()):
            lines.append(f"- {status}: {cnt}")
        lines.append("")

        if loss_reports:
            lines.append("## Details")
            lines.append("")
            for idx, report in enumerate(loss_reports):
                if report.losses:
                    lines.append(f"### Record {idx}")
                    lines.append(f"- Status: {report.status.value}")
                    lines.append(f"- Target: {report.target}")
                    for loss in report.losses:
                        lines.append(f"  - [{loss.severity.value}] {loss.code}: {loss.message}")
                        if loss.field:
                            lines.append(f"    - Field: {loss.field}")
                        if loss.suggestion:
                            lines.append(f"    - Suggestion: {loss.suggestion}")
                    lines.append("")

        loss_report.write_text("\n".join(lines))
        console.print(f"  Loss report written to {loss_report}")
