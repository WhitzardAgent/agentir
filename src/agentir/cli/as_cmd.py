"""agentir-as: frontend parser command (source -> RawIR/ParsedIR)."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn

from agentir.io.jsonl import write_jsonl
from agentir.io.parquet import write_parquet

app = typer.Typer(
    name="agentir-as",
    help="Parse source datasets into AgentIR (.air.jsonl / .air.parquet).",
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


def _record_to_dict(record) -> dict:
    """Serialize an AgentIRRecord to a dict, filtering None values."""
    data = record.model_dump(mode="json")
    return {k: v for k, v in data.items() if v is not None}


@app.command()
def main(
    frontend: Annotated[
        str, typer.Option("--frontend", help="Frontend parser name.", show_default=False)
    ],
    input: Annotated[Path | None, typer.Option("--input", help="Local input file path.")] = None,
    hf_dataset: Annotated[
        str | None, typer.Option("--hf-dataset", help="Hugging Face dataset ID.")
    ] = None,
    config: Annotated[str | None, typer.Option("--config", help="HF dataset config name.")] = None,
    split: Annotated[str, typer.Option("--split", help="Dataset split.")] = "train",
    streaming: Annotated[
        bool, typer.Option("--streaming/--no-streaming", help="Use HF streaming mode.")
    ] = True,
    limit: Annotated[int | None, typer.Option("--limit", help="Max records to process.")] = None,
    output: Annotated[
        Path, typer.Option("--output", help="Output file path.", show_default=False)
    ] = ...,
    format: Annotated[
        str | None, typer.Option("--format", help="Output format: jsonl|parquet.")
    ] = None,
    strict: Annotated[
        bool, typer.Option("--strict/--no-strict", help="Fail on parse errors.")
    ] = False,
    debug: Annotated[
        bool, typer.Option("--debug/--no-debug", help="Include verbose diagnostics.")
    ] = False,
) -> None:
    """Parse source datasets into AgentIR intermediate representation."""
    console = Console()

    # Validate mutually-exclusive input sources
    if input is None and hf_dataset is None:
        err_console.print("[red]Error:[/red] Must provide --input or --hf-dataset.")
        raise typer.Exit(code=2)
    if input is not None and hf_dataset is not None:
        err_console.print("[red]Error:[/red] Cannot specify both --input and --hf-dataset.")
        raise typer.Exit(code=2)

    # Ensure frontends are imported so they register
    import importlib

    for mod_name in [
        "agentir.frontends.agenttrove",
        "agentir.frontends.claude_code",
        "agentir.frontends.codex_swebenchpro",
        "agentir.frontends.hermes_agent",
        "agentir.frontends.openhands",
        "agentir.frontends.sharegpt",
    ]:
        try:
            importlib.import_module(mod_name)
        except Exception:
            pass

    from agentir.frontends.registry import get_frontend, list_frontends

    # Resolve frontend
    fe = get_frontend(frontend)
    if fe is None:
        available = ", ".join(list_frontends()) or "(none)"
        err_console.print(
            f"[red]Error:[/red] Unknown frontend '{frontend}'. Available: {available}"
        )
        raise typer.Exit(code=3)

    fmt = _infer_format(output, format)

    from agentir.diagnostics.reporter import DiagnosticReporter
    from agentir.frontends.base import FrontendContext
    from agentir.io.jsonl import read_jsonl as _read_jsonl

    reporter = DiagnosticReporter()
    records_out: list[dict] = []
    total_parsed = 0
    total_errors = 0

    # Build record iterator from the chosen source
    if hf_dataset is not None:
        from agentir.io.hf import load_hf_dataset

        console.print(f"Loading HF dataset [bold]{hf_dataset}[/bold] (split={split})")
        if config:
            console.print(f"  config: {config}")
        row_iter = load_hf_dataset(
            hf_dataset,
            config=config,
            split=split,
            streaming=streaming,
            limit=limit,
        )
    else:
        if not input.exists():  # type: ignore[union-attr]
            err_console.print(f"[red]Error:[/red] Input file not found: {input}")
            raise typer.Exit(code=2)
        row_iter = _read_jsonl(input, limit=limit)

    # Process records
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Parsing records...", total=limit)

        for row_idx, row in enumerate(row_iter):
            ctx = FrontendContext(
                dataset=hf_dataset,
                config=config,
                split=split,
                row_index=row_idx,
                strict=strict,
            )
            result = fe.parse_record(row, ctx)

            # Collect diagnostics
            if result.diagnostics:
                reporter.add_all(result.diagnostics)

            if result.record is not None:
                records_out.append(_record_to_dict(result.record))
                total_parsed += 1
            else:
                total_errors += 1
                if strict:
                    reporter.print_diagnostics()
                    err_console.print(f"[red]Parse error at row {row_idx} (strict mode).[/red]")
                    raise typer.Exit(code=1)

            progress.advance(task)

            # Periodic progress for unlimited streams
            if limit is None and (row_idx + 1) % 100 == 0:
                console.print(f"  Parsed {row_idx + 1} records...")

    # Write output
    if fmt == "parquet":
        count = write_parquet(output, records_out)
    else:
        count = write_jsonl(output, iter(records_out))

    # Summary
    console.print()
    console.print(f"[bold green]Done.[/bold green] Wrote {count} records to {output}")
    if total_errors:
        console.print(f"  [yellow]{total_errors} records had parse errors.[/yellow]")

    if debug or reporter.has_errors:
        reporter.print_summary()

    if reporter.has_errors:
        raise typer.Exit(code=1)
