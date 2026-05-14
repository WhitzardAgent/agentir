"""CLI commands for the AgentIR Format DSL."""

from __future__ import annotations

import json
import time
import sys
import os
from pathlib import Path
from typing import Any, Optional, Annotated

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress
from rich.tree import Tree
from rich import box
from rich.syntax import Syntax

from agentir.diagnostics.diagnostic import Diagnostic
from agentir.dsl.loader import load_dsl, validate_dsl
from agentir.dsl.compiler import compile_dsl_frontend
from agentir.dsl.models import TrajectoryFormat
from agentir.frontends.registry import list_frontends
from agentir.frontends.base import FrontendContext
from agentir.ir.base import DiagnosticSeverity
from agentir.ir.record import AgentIRRecord

# ---------------------------------------------------------------------------
# Console setup
# ---------------------------------------------------------------------------

console = Console()
err_console = Console(stderr=True)
dsl_app = typer.Typer(name="dsl", help="DSL format definition commands")


# ---------------------------------------------------------------------------
# Helper: read JSON / JSONL records
# ---------------------------------------------------------------------------


def _read_records(path: str, limit: Optional[int] = None) -> list[dict]:
    """Read JSONL (one JSON object per line) or JSON (single object or array).

    Args:
        path: Path to the input file.
        limit: Maximum number of records to return.

    Returns:
        A list of dict records.

    Raises:
        FileNotFoundError: if the file does not exist.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Input file not found: {path}")

    with open(p, "r", encoding="utf-8") as fh:
        raw = fh.read()

    records: list[dict] = []

    # If the file starts with '[' it is a JSON array.
    stripped = raw.strip()
    if stripped.startswith("["):
        data = json.loads(stripped)
        if isinstance(data, list):
            records = data
    elif stripped.startswith("{"):
        # Could be a single JSON object or JSONL.
        # Try single object first.
        try:
            obj = json.loads(stripped)
            if isinstance(obj, dict):
                records = [obj]
        except json.JSONDecodeError:
            # Fall through to JSONL parsing.
            pass

    if not records:
        # JSONL: one JSON object per line.
        for line in stripped.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    records.append(obj)
            except json.JSONDecodeError:
                continue

    if limit is not None and len(records) > limit:
        records = records[:limit]

    return records


# ---------------------------------------------------------------------------
# Helper: write JSONL
# ---------------------------------------------------------------------------


def _write_jsonl(path: str, records: list[dict]) -> int:
    """Write a list of dicts as JSONL (one JSON object per line).

    Returns:
        Number of records written.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False))
            fh.write("\n")
    return len(records)


# ---------------------------------------------------------------------------
# Helper: serialise AgentIRRecord to dict
# ---------------------------------------------------------------------------


def _record_to_dict(record: AgentIRRecord) -> dict:
    """Convert an AgentIRRecord to a JSON-serialisable dict."""
    data = record.model_dump(mode="json", exclude_none=True)
    return data


# ---------------------------------------------------------------------------
# Helper: build field tree from a record
# ---------------------------------------------------------------------------


def _build_field_tree(obj: Any, prefix: str = "$", depth: int = 0,
                      max_depth: int = 4) -> Tree:
    """Recursively build a Rich Tree from a nested dict/list/primitive.

    Args:
        obj: The value to inspect.
        prefix: JSON-path prefix for the root node.
        depth: Current nesting depth.
        max_depth: Maximum depth to recurse.

    Returns:
        A :class:`rich.tree.Tree` instance.
    """
    label_parts: list[str] = [prefix]

    if obj is None:
        label_parts.append("[dim]null[/dim]")
    elif isinstance(obj, str):
        preview = obj[:60] + ("..." if len(obj) > 60 else "")
        label_parts.append(f"[green]str[/green] [dim]\"{preview}\"[/dim]")
    elif isinstance(obj, bool):
        label_parts.append(f"[yellow]bool[/yellow] [dim]{obj}[/dim]")
    elif isinstance(obj, int):
        label_parts.append(f"[cyan]int[/cyan] [dim]{obj}[/dim]")
    elif isinstance(obj, float):
        label_parts.append(f"[cyan]float[/cyan] [dim]{obj:.4g}[/dim]")
    elif isinstance(obj, list):
        label_parts.append(f"[magenta]list[{len(obj)}][/magenta]")
    elif isinstance(obj, dict):
        label_parts.append(f"[blue]dict[{len(obj)} keys][/blue]")
    else:
        label_parts.append(f"[dim]{type(obj).__name__}[/dim]")

    tree = Tree(" ".join(label_parts))

    if depth >= max_depth:
        if isinstance(obj, (list, dict)):
            tree.add("[dim]... (truncated)[/dim]")
        return tree

    if isinstance(obj, dict):
        for key, val in list(obj.items())[:20]:
            tree.add(_build_field_tree(val, prefix=f".{key}", depth=depth + 1,
                                        max_depth=max_depth))
        if len(obj) > 20:
            tree.add(f"[dim]... and {len(obj) - 20} more keys[/dim]")
    elif isinstance(obj, list):
        limit = min(len(obj), 10)
        for i in range(limit):
            tree.add(_build_field_tree(obj[i], prefix=f"[{i}]", depth=depth + 1,
                                        max_depth=max_depth))
        if len(obj) > 10:
            tree.add(f"[dim]... and {len(obj) - 10} more items[/dim]")

    return tree


# ============================================================================
# Subcommands
# ============================================================================


def _find_format_specs() -> list[Path]:
    """Find all ``*.agentir.yaml`` files in known locations."""
    candidates = [
        Path("dsl/formats"),
        Path("dsl/templates"),
        Path("examples"),
    ]
    result: list[Path] = []
    for d in candidates:
        if d.is_dir():
            result.extend(sorted(d.rglob("*.agentir.yaml")))
    if not result and Path("dsl").is_dir():
        result.extend(sorted(Path("dsl").rglob("*.agentir.yaml")))
    return result


# ---------------------------------------------------------------------------
# 1. validate
# ---------------------------------------------------------------------------


@dsl_app.command()
def validate(
    dsl_file: Annotated[
        str,
        typer.Argument(help="Path to *.agentir.yaml file.", show_default=False),
    ],
) -> None:
    """Validate a DSL format definition file.

    Checks required top-level fields, apiVersion compatibility, episode
    presence, and performs full Pydantic validation.

    Example:
        agentir dsl validate my_format.agentir.yaml
    """
    path = Path(dsl_file)

    if not path.exists():
        err_console.print(f"[red]ERROR:[/red] File not found: {dsl_file}")
        raise typer.Exit(code=2)

    console.print(f"[bold]Validating DSL file:[/bold] {dsl_file}")
    console.print()

    valid, diagnostics = validate_dsl(str(path))

    if valid:
        console.print(Panel.fit(
            "[bold green]PASS[/bold green]",
            title="Validation Result",
            border_style="green",
        ))
    else:
        console.print(Panel.fit(
            "[bold red]FAIL[/bold red]",
            title="Validation Result",
            border_style="red",
        ))

    if diagnostics:
        console.print()
        console.print("[bold]Diagnostics:[/bold]")
        table = Table(show_header=True, box=box.ROUNDED)
        table.add_column("Severity", style="bold", width=10)
        table.add_column("Code", width=12)
        table.add_column("Message")

        for diag in diagnostics:
            if diag.severity == DiagnosticSeverity.ERROR:
                sev_icon = "[bold red]ERROR[/bold red]"
            elif diag.severity == DiagnosticSeverity.WARNING:
                sev_icon = "[bold yellow]WARN [/bold yellow]"
            elif diag.severity == DiagnosticSeverity.FATAL:
                sev_icon = "[bold red]FATAL[/bold red]"
            else:
                sev_icon = "[dim]INFO [/dim]"

            table.add_row(sev_icon, diag.code, diag.message)

        console.print(table)

    console.print()
    if valid:
        console.print("[green]DSL file is valid.[/green]")
        raise typer.Exit(code=0)
    else:
        error_count = sum(
            1 for d in diagnostics if d.severity in
            (DiagnosticSeverity.ERROR, DiagnosticSeverity.FATAL)
        )
        console.print(f"[red]DSL file has {error_count} error(s).[/red]")
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# 2. probe
# ---------------------------------------------------------------------------


@dsl_app.command()
def probe(
    input_path: Annotated[
        str,
        typer.Argument(help="Path to input data file (JSON or JSONL).",
                       show_default=False),
    ],
    dsl_file: Annotated[
        Optional[str],
        typer.Option("--dsl", help="Path to *.agentir.yaml for detection scoring."),
    ] = None,
    limit: Annotated[
        int,
        typer.Option("--limit", "-n", help="Maximum records to probe."),
    ] = 5,
) -> None:
    """Probe the structure of an input data file.

    Displays the field tree (paths, types, and sample values) for the
    first few records. If a DSL file is provided, also runs detection
    scoring and prints the results.

    Example:
        agentir dsl probe data.jsonl --dsl my_format.agentir.yaml -n 3
    """
    try:
        records = _read_records(input_path, limit=limit)
    except FileNotFoundError as e:
        err_console.print(f"[red]ERROR:[/red] {e}")
        raise typer.Exit(code=2)
    except json.JSONDecodeError as e:
        err_console.print(f"[red]ERROR:[/red] Failed to parse {input_path}: {e}")
        raise typer.Exit(code=2)

    console.print(f"[bold]Probing:[/bold] {input_path}")
    console.print(f"  Records read: {len(records)}")
    console.print()

    if not records:
        console.print("[yellow]No records found in input file.[/yellow]")
        return

    if len(records) == 1:
        console.print("[bold]Field tree for record 1:[/bold]")
        console.print(_build_field_tree(records[0]))
    else:
        console.print("[bold]Field tree for first record:[/bold]")
        console.print(_build_field_tree(records[0]))
        console.print()
        console.print(f"[dim]({len(records) - 1} additional record(s) available)[/dim]")

    # ---- Detection scoring ----
    if dsl_file is not None:
        dsl_path = Path(dsl_file)
        if not dsl_path.exists():
            err_console.print(f"[red]ERROR:[/red] DSL file not found: {dsl_file}")
            raise typer.Exit(code=3)

        try:
            spec = load_dsl(str(dsl_path))
        except Exception as e:
            err_console.print(f"[red]ERROR:[/red] Failed to load DSL: {e}")
            raise typer.Exit(code=1)

        frontend = compile_dsl_frontend(spec, str(dsl_path))

        console.print()
        console.print(f"[bold]Detection scoring (DSL: {dsl_file}):[/bold]")
        score_table = Table(show_header=True, box=box.ROUNDED)
        score_table.add_column("Record #", style="dim", width=10)
        score_table.add_column("Score", style="bold", width=10)
        score_table.add_column("Verdict", width=12)

        for i, rec in enumerate(records):
            score = frontend.detect(rec)
            verdict = (
                "[green]MATCH[/green]" if score >= spec.detect.min_score
                else "[yellow]LOW [/yellow]"
            )
            score_table.add_row(str(i + 1), f"{score:.2f}", verdict)

        console.print(score_table)
        console.print(f"  Min required score: {spec.detect.min_score}")


# ---------------------------------------------------------------------------
# 3. preview
# ---------------------------------------------------------------------------


@dsl_app.command()
def preview(
    dsl_file: Annotated[
        str,
        typer.Argument(help="Path to *.agentir.yaml file.", show_default=False),
    ],
    input_path: Annotated[
        str,
        typer.Argument(help="Path to input data file (JSON or JSONL).",
                       show_default=False),
    ],
    limit: Annotated[
        int,
        typer.Option("--limit", "-n", help="Maximum records to preview."),
    ] = 5,
    show_events: Annotated[
        bool,
        typer.Option("--show-events/--no-show-events",
                     help="Display event detail cards."),
    ] = False,
) -> None:
    """Preview conversion results for a few records.

    Loads the DSL spec, compiles it to a runtime frontend, and converts
    up to *limit* records from the input. Displays a summary table and
    optionally event detail cards.

    Example:
        agentir dsl preview my_fmt.agentir.yaml data.jsonl -n 5 --show-events
    """
    dsl_path = Path(dsl_file)
    if not dsl_path.exists():
        err_console.print(f"[red]ERROR:[/red] DSL file not found: {dsl_file}")
        raise typer.Exit(code=2)

    try:
        spec = load_dsl(str(dsl_path))
    except Exception as e:
        err_console.print(f"[red]ERROR:[/red] Failed to load DSL: {e}")
        raise typer.Exit(code=1)

    frontend = compile_dsl_frontend(spec, str(dsl_path))

    try:
        records = _read_records(input_path, limit=limit)
    except FileNotFoundError as e:
        err_console.print(f"[red]ERROR:[/red] {e}")
        raise typer.Exit(code=2)

    console.print(f"[bold]Preview:[/bold] {spec.metadata.name}")
    console.print(f"  DSL: {dsl_file}")
    console.print(f"  Input: {input_path} ({len(records)} record(s))")
    console.print()

    # ---- Summary table ----
    table = Table(show_header=True, box=box.ROUNDED, title="Conversion Preview")
    table.add_column("Record ID", style="bold cyan", width=30)
    table.add_column("Events", justify="right", width=8)
    table.add_column("Event Types", width=40)
    table.add_column("Roles", width=40)

    for i, rec in enumerate(records):
        ctx = FrontendContext(
            dataset=None,
            config=None,
            split=None,
            row_index=i,
        )
        result = frontend.parse_record(rec, ctx)

        if result.record is None:
            table.add_row(
                "[red](no record)[/red]",
                "-", "-", "-"
            )
            continue

        air = result.record
        events = []
        for ep in air.episodes:
            events.extend(ep.events)

        event_count = len(events)
        event_types = list(dict.fromkeys(
            e.event_type.value if hasattr(e.event_type, "value")
            else str(e.event_type)
            for e in events
        ))
        roles_list = list(dict.fromkeys(
            e.role.value if hasattr(e.role, "value") else str(e.role)
            for e in events
        ))

        table.add_row(
            air.record_id,
            str(event_count),
            ", ".join(event_types[:5]) + (
                "..." if len(event_types) > 5 else ""
            ),
            ", ".join(roles_list[:5]) + (
                "..." if len(roles_list) > 5 else ""
            ),
        )

    console.print(table)

    # ---- Event detail cards ----
    if show_events:
        console.print()
        console.print("[bold]Event details:[/bold]")

        for i, rec in enumerate(records):
            ctx = FrontendContext(
                dataset=None,
                config=None,
                split=None,
                row_index=i,
            )
            result = frontend.parse_record(rec, ctx)

            if result.record is None:
                continue

            air = result.record
            all_events: list[Any] = []
            for ep in air.episodes:
                all_events.extend(ep.events)

            if not all_events:
                console.print(f"  [dim]Record {air.record_id}: no events[/dim]")
                continue

            console.print()
            console.print(f"  [bold]Record: {air.record_id}[/bold] "
                          f"({len(all_events)} event(s))")

            for evt in all_events[:10]:
                et = (evt.event_type.value
                      if hasattr(evt.event_type, "value")
                      else str(evt.event_type))
                rl = (evt.role.value
                      if hasattr(evt.role, "value")
                      else str(evt.role))

                content_preview = ""
                if evt.content:
                    first_block = evt.content[0]
                    if hasattr(first_block, "text") and first_block.text:
                        content_preview = first_block.text[:120]
                        if len(first_block.text) > 120:
                            content_preview += "..."

                panel_content = (
                    f"[bold]Type:[/bold] {et}\n"
                    f"[bold]Role:[/bold] {rl}\n"
                    f"[bold]ID:[/bold] {evt.event_id}\n"
                    f"[bold]Content:[/bold] {content_preview}"
                )

                console.print(Panel(
                    panel_content,
                    title=f"Event {evt.idx}",
                    border_style="dim blue",
                    width=80,
                ))

            if len(all_events) > 10:
                console.print(
                    f"  [dim]... and {len(all_events) - 10}"
                    f" more event(s)[/dim]"
                )

    console.print()
    console.print("[dim]Use 'agentir dsl convert' to perform full conversion.[/dim]")


# ---------------------------------------------------------------------------
# 4. convert
# ---------------------------------------------------------------------------


@dsl_app.command()
def convert(
    dsl_file: Annotated[
        str,
        typer.Argument(help="Path to *.agentir.yaml file.", show_default=False),
    ],
    input_path: Annotated[
        str,
        typer.Argument(help="Path to input data file (JSON or JSONL).",
                       show_default=False),
    ],
    output_path: Annotated[
        str,
        typer.Option("--output", "-o", help="Output path for AgentIR JSONL."),
    ] = "out.air.jsonl",
) -> None:
    """Full conversion using a DSL definition.

    Reads every record from the input file, converts it through the DSL
    runtime frontend, and writes AgentIR JSONL to the output path.

    Example:
        agentir dsl convert my_fmt.agentir.yaml data.jsonl -o out.air.jsonl
    """
    dsl_path = Path(dsl_file)
    if not dsl_path.exists():
        err_console.print(f"[red]ERROR:[/red] DSL file not found: {dsl_file}")
        raise typer.Exit(code=2)

    try:
        spec = load_dsl(str(dsl_path))
    except Exception as e:
        err_console.print(f"[red]ERROR:[/red] Failed to load DSL: {e}")
        raise typer.Exit(code=1)

    frontend = compile_dsl_frontend(spec, str(dsl_path))

    try:
        records = _read_records(input_path)
    except FileNotFoundError as e:
        err_console.print(f"[red]ERROR:[/red] {e}")
        raise typer.Exit(code=2)

    total_records = len(records)
    console.print(f"[bold]Conversion:[/bold] {spec.metadata.name}")
    console.print(f"  Input: {input_path} ({total_records} record(s))")
    console.print(f"  Output: {output_path}")
    console.print()

    out_records: list[dict] = []
    total_events = 0
    failures = 0

    with Progress() as progress:
        task = progress.add_task("[cyan]Converting...", total=total_records)
        started_at = time.time()

        for i, rec in enumerate(records):
            ctx = FrontendContext(
                dataset=None,
                config=None,
                split=None,
                row_index=i,
            )

            try:
                result = frontend.parse_record(rec, ctx)

                if result.record is not None:
                    out_records.append(_record_to_dict(result.record))
                    event_count = sum(
                        len(ep.events) for ep in result.record.episodes
                    )
                    total_events += event_count
                else:
                    failures += 1
            except Exception:
                failures += 1

            progress.update(task, advance=1)

    elapsed = time.time() - started_at

    _write_jsonl(output_path, out_records)

    success_count = total_records - failures
    rate = success_count / elapsed if elapsed > 0 else float("inf")

    console.print()
    console.print("[bold green]Conversion complete.[/bold green]")
    console.print()

    stats_table = Table(show_header=False, box=box.SIMPLE)
    stats_table.add_column("Metric", style="bold", width=20)
    stats_table.add_column("Value")

    stats_table.add_row("Total records", str(total_records))
    stats_table.add_row("Successful", str(success_count))
    stats_table.add_row("Failures", str(failures))
    stats_table.add_row("Events emitted", str(total_events))
    stats_table.add_row("Duration", f"{elapsed:.2f}s")
    stats_table.add_row("Rate", f"{rate:.1f} rec/s")

    console.print(stats_table)
    console.print()
    console.print(f"[bold]Output written to:[/bold] {output_path}")


# ---------------------------------------------------------------------------
# 5. bench
# ---------------------------------------------------------------------------


@dsl_app.command()
def bench(
    dsl_file: Annotated[
        str,
        typer.Argument(help="Path to *.agentir.yaml file.", show_default=False),
    ],
    input_path: Annotated[
        str,
        typer.Argument(help="Path to input data file (JSON or JSONL).",
                       show_default=False),
    ],
    limit: Annotated[
        Optional[int],
        typer.Option("--limit", "-n", help="Maximum records to benchmark."),
    ] = None,
) -> None:
    """Benchmark DSL conversion performance.

    Times the conversion and prints records/sec, events/sec, total time,
    and approximate memory usage.

    Example:
        agentir dsl bench my_fmt.agentir.yaml data.jsonl -n 1000
    """
    dsl_path = Path(dsl_file)
    if not dsl_path.exists():
        err_console.print(f"[red]ERROR:[/red] DSL file not found: {dsl_file}")
        raise typer.Exit(code=2)

    try:
        spec = load_dsl(str(dsl_path))
    except Exception as e:
        err_console.print(f"[red]ERROR:[/red] Failed to load DSL: {e}")
        raise typer.Exit(code=1)

    frontend = compile_dsl_frontend(spec, str(dsl_path))

    try:
        records = _read_records(input_path, limit=limit)
    except FileNotFoundError as e:
        err_console.print(f"[red]ERROR:[/red] {e}")
        raise typer.Exit(code=2)

    total = len(records)
    console.print(f"[bold]Benchmark:[/bold] {spec.metadata.name}")
    console.print(f"  Input: {input_path} ({total} record(s))")
    console.print()

    # Counters
    total_events = 0
    failures = 0

    # Warm-up: process up to 5 records silently
    warmup_n = min(5, total)
    for i in range(warmup_n):
        try:
            ctx = FrontendContext(
                dataset=None, config=None, split=None, row_index=i
            )
            frontend.parse_record(records[i], ctx)
        except Exception:
            pass

    # Timed run
    started_at = time.perf_counter()

    for i, rec in enumerate(records):
        ctx = FrontendContext(
            dataset=None, config=None, split=None, row_index=i
        )
        try:
            result = frontend.parse_record(rec, ctx)
            if result.record is not None:
                total_events += sum(
                    len(ep.events) for ep in result.record.episodes
                )
            else:
                failures += 1
        except Exception:
            failures += 1

    elapsed = time.perf_counter() - started_at
    success = total - failures

    recs_per_sec = success / elapsed if elapsed > 0 else float("inf")
    evts_per_sec = total_events / elapsed if elapsed > 0 else float("inf")

    # Approximate memory (rough estimate)
    try:
        approx_mem_bytes = sys.getsizeof(records)
        for rec in records[:100]:
            approx_mem_bytes += sys.getsizeof(rec)
        approx_mem_mb = approx_mem_bytes / (1024 * 1024)
    except Exception:
        approx_mem_mb = 0.0

    console.print()
    bench_table = Table(show_header=False, box=box.SIMPLE_HEAVY)
    bench_table.add_column("Metric", style="bold", width=22)
    bench_table.add_column("Value", justify="right")

    bench_table.add_row("Total records", str(total))
    bench_table.add_row("Successful", str(success))
    bench_table.add_row("Failures", str(failures))
    bench_table.add_row("Events emitted", str(total_events))
    bench_table.add_row("Total time", f"{elapsed:.4f}s")
    bench_table.add_row("Records/sec", f"{recs_per_sec:.1f}")
    bench_table.add_row("Events/sec", f"{evts_per_sec:.1f}")
    bench_table.add_row("Approx. memory", f"{approx_mem_mb:.1f} MB")

    console.print(bench_table)


# ---------------------------------------------------------------------------
# 6. diff
# ---------------------------------------------------------------------------


@dsl_app.command()
def diff(
    dsl_file_a: Annotated[
        str,
        typer.Argument(help="Path to first *.agentir.yaml file.",
                       show_default=False),
    ],
    dsl_file_b: Annotated[
        str,
        typer.Argument(help="Path to second *.agentir.yaml file.",
                       show_default=False),
    ],
    input_path: Annotated[
        str,
        typer.Argument(help="Path to input data file (JSON or JSONL).",
                       show_default=False),
    ],
) -> None:
    """Compare two DSL definitions on the same input.

    Loads both DSL specs, converts the same input records, and shows a
    side-by-side comparison table with event count deltas and event type
    differences.

    Example:
        agentir dsl diff v1.agentir.yaml v2.agentir.yaml data.jsonl
    """
    path_a = Path(dsl_file_a)
    path_b = Path(dsl_file_b)

    if not path_a.exists():
        err_console.print(f"[red]ERROR:[/red] DSL file not found: {dsl_file_a}")
        raise typer.Exit(code=2)
    if not path_b.exists():
        err_console.print(f"[red]ERROR:[/red] DSL file not found: {dsl_file_b}")
        raise typer.Exit(code=2)

    try:
        spec_a = load_dsl(str(path_a))
        spec_b = load_dsl(str(path_b))
    except Exception as e:
        err_console.print(f"[red]ERROR:[/red] Failed to load DSL: {e}")
        raise typer.Exit(code=1)

    frontend_a = compile_dsl_frontend(spec_a, str(path_a))
    frontend_b = compile_dsl_frontend(spec_b, str(path_b))

    try:
        records = _read_records(input_path)
    except FileNotFoundError as e:
        err_console.print(f"[red]ERROR:[/red] {e}")
        raise typer.Exit(code=2)

    total = len(records)
    console.print(
        f"[bold]DSL Diff:[/bold] {spec_a.metadata.name} "
        f"vs {spec_b.metadata.name}"
    )
    console.print(f"  Input: {input_path} ({total} record(s))")
    console.print()

    table = Table(show_header=True, box=box.ROUNDED, title="Comparison")
    table.add_column("Record ID", style="bold cyan", width=30)
    table.add_column("A: events", justify="right", width=10)
    table.add_column("B: events", justify="right", width=10)
    table.add_column("Delta", justify="right", width=8)
    table.add_column("Event types in A only", width=30)
    table.add_column("Event types in B only", width=30)

    for i, rec in enumerate(records):
        ctx = FrontendContext(
            dataset=None, config=None, split=None, row_index=i
        )

        try:
            res_a = frontend_a.parse_record(rec, ctx)
            res_b = frontend_b.parse_record(rec, ctx)
        except Exception:
            table.add_row(f"[red](error {i})[/red]", "-", "-", "-", "-", "-")
            continue

        evts_a = []
        evts_b = []
        if res_a.record:
            for ep in res_a.record.episodes:
                evts_a.extend(ep.events)
        if res_b.record:
            for ep in res_b.record.episodes:
                evts_b.extend(ep.events)

        count_a = len(evts_a)
        count_b = len(evts_b)
        delta = count_b - count_a
        if delta > 0:
            delta_str = f"[red]+{delta}[/red]"
        elif delta < 0:
            delta_str = f"[green]{delta}[/green]"
        else:
            delta_str = "[dim]0[/dim]"

        types_a = set(
            e.event_type.value
            if hasattr(e.event_type, "value")
            else str(e.event_type)
            for e in evts_a
        )
        types_b = set(
            e.event_type.value
            if hasattr(e.event_type, "value")
            else str(e.event_type)
            for e in evts_b
        )
        only_a = types_a - types_b
        only_b = types_b - types_a

        rec_id = (
            res_a.record.record_id
            if res_a.record
            else (res_b.record.record_id if res_b.record else f"row-{i}")
        )

        table.add_row(
            rec_id,
            str(count_a),
            str(count_b),
            delta_str,
            ", ".join(sorted(only_a)) if only_a else "[dim]--[/dim]",
            ", ".join(sorted(only_b)) if only_b else "[dim]--[/dim]",
        )

    console.print(table)

    # Aggregate summary
    total_a = 0
    total_b = 0
    all_types_a: set[str] = set()
    all_types_b: set[str] = set()

    for i, rec in enumerate(records):
        ctx = FrontendContext(
            dataset=None, config=None, split=None, row_index=i
        )
        try:
            res_a = frontend_a.parse_record(rec, ctx)
            res_b = frontend_b.parse_record(rec, ctx)
        except Exception:
            continue
        if res_a.record:
            for ep in res_a.record.episodes:
                total_a += len(ep.events)
                for e in ep.events:
                    all_types_a.add(
                        e.event_type.value
                        if hasattr(e.event_type, "value")
                        else str(e.event_type)
                    )
        if res_b.record:
            for ep in res_b.record.episodes:
                total_b += len(ep.events)
                for e in ep.events:
                    all_types_b.add(
                        e.event_type.value
                        if hasattr(e.event_type, "value")
                        else str(e.event_type)
                    )

    console.print()
    summary_table = Table(
        show_header=False, box=box.SIMPLE, title="Aggregate"
    )
    summary_table.add_column("Metric", style="bold", width=22)
    summary_table.add_column("Value")

    summary_table.add_row("Total events (A)", str(total_a))
    summary_table.add_row("Total events (B)", str(total_b))
    summary_table.add_row("Delta", f"{total_b - total_a:+d}")
    summary_table.add_row(
        "Unique event types (A)", str(len(all_types_a))
    )
    summary_table.add_row(
        "Unique event types (B)", str(len(all_types_b))
    )
    summary_table.add_row(
        "Types only in A",
        ", ".join(sorted(all_types_a - all_types_b)) or "(none)",
    )
    summary_table.add_row(
        "Types only in B",
        ", ".join(sorted(all_types_b - all_types_a)) or "(none)",
    )

    console.print(summary_table)


# ---------------------------------------------------------------------------
# 7. init
# ---------------------------------------------------------------------------


_INIT_TEMPLATE = """apiVersion: agentir.qitor.ai/v0.1
kind: TrajectoryFormat
metadata:
  name: {name}
  title: {title}
  version: "0.1.0"
  description: {description}
  owners:
    - {owner}
  tags:
    - agentir
    - trajectory
source:
  kind: jsonl
  record_mode: row
  framework: {framework}
  raw_policy: full
detect:
  min_score: 0.70
  rules:
    # Example: score a record higher if it has "messages"
    - field_exists: "$.messages"
      score: 0.40
    # Example: score higher if messages is a list
    - field_is_list: "$.messages"
      score: 0.30
episodes:
  - episode_id:
      template: "ep_{{idx}}"
    events:
      - foreach:
          path: "$.messages[*]"
        as: turn
        emit:
          event_id:
            template: "evt_{{{{i}}}}"
          event_type:
            transform: role_to_event_type
            input:
              path: "turn.role"
          role:
            path: "turn.role"
          content:
            path: "turn.content"
"""


@dsl_app.command()
def init(
    output_path: Annotated[
        Path,
        typer.Argument(help="Path for the new *.agentir.yaml file."),
    ],
    name: Annotated[
        str, typer.Option("--name", help="Format name (kebab-case).")
    ] = "my-format",
    title: Annotated[
        str, typer.Option("--title", help="Human-readable title.")
    ] = "My Format",
    framework: Annotated[
        str, typer.Option("--framework", help="Origin framework name.")
    ] = "custom",
    description: Annotated[
        str, typer.Option("--description", help="Description of the format.")
    ] = "A custom trajectory format definition.",
    owner: Annotated[
        str, typer.Option("--owner", help="Format owner username.")
    ] = "developer",
    force: Annotated[
        bool, typer.Option("--force", "-f", help="Overwrite existing file.")
    ] = False,
) -> None:
    """Create a new *.agentir.yaml DSL file from a template."""
    if output_path.exists() and not force:
        err_console.print(
            f"[red]Error:[/red] {output_path} already exists. Use --force to overwrite."
        )
        raise typer.Exit(code=2)

    content = _INIT_TEMPLATE.format(
        name=name,
        title=title,
        framework=framework,
        description=description,
        owner=owner,
    )

    output_path.write_text(content, encoding="utf-8")
    console.print(f"[bold green]Created:[/bold green] {output_path}")
    console.print()
    console.print("Next steps:")
    console.print(f"  1. Edit the file to match your data: {output_path}")
    console.print(f"  2. Validate: agentir dsl validate {output_path}")
    console.print(f"  3. Probe your data: agentir dsl probe <input.jsonl> --dsl {output_path}")
    console.print(f"  4. Preview conversion: agentir dsl preview <input.jsonl> {output_path}")

    raise typer.Exit(code=0)


# ---------------------------------------------------------------------------
# dsl formats (list/show)
# ---------------------------------------------------------------------------


@dsl_app.command("formats")
def formats_list(
    show_details: Annotated[
        bool, typer.Option("--details", "-d", help="Show full details of each format.")
    ] = False,
) -> None:
    """List available DSL format specifications found on disk."""
    paths = _find_format_specs()

    if not paths:
        console.print("[yellow]No *.agentir.yaml files found.[/yellow]")
        raise typer.Exit(code=0)

    console.print()
    console.print(f"[bold]Found {len(paths)} format spec(s):[/bold]")
    console.print()

    table = Table(title="Available DSL Formats", box=box.SIMPLE)
    table.add_column("File", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Version", style="dim")
    table.add_column("Source Kind", style="yellow")
    table.add_column("Framework", style="magenta")

    for p in paths:
        try:
            spec = load_dsl(p)
            table.add_row(
                str(p),
                spec.metadata.name,
                spec.metadata.version,
                spec.source.kind,
                spec.source.framework or "-",
            )
        except Exception:
            table.add_row(str(p), "[red](invalid)[/red]", "-", "-", "-")

    console.print(table)

    if show_details:
        for p in paths:
            try:
                spec = load_dsl(p)
            except Exception:
                continue

            console.print()
            console.print(Panel(f"[bold]{p}[/bold]", border_style="blue"))

            info_table = Table(box=None, show_header=False)
            info_table.add_column("Key", style="cyan")
            info_table.add_column("Value", style="white")

            info_table.add_row("Name", spec.metadata.name)
            if spec.metadata.title:
                info_table.add_row("Title", spec.metadata.title)
            if spec.metadata.description:
                info_table.add_row("Description", spec.metadata.description)
            info_table.add_row("Version", spec.metadata.version)
            if spec.metadata.owners:
                info_table.add_row("Owners", ", ".join(spec.metadata.owners))
            if spec.metadata.tags:
                info_table.add_row("Tags", ", ".join(spec.metadata.tags))
            info_table.add_row("Source Kind", spec.source.kind)
            info_table.add_row("Record Mode", spec.source.record_mode)
            if spec.source.framework:
                info_table.add_row("Framework", spec.source.framework)
            if spec.source.format:
                info_table.add_row("Format", spec.source.format)
            if spec.source.license:
                info_table.add_row("License", spec.source.license)
            info_table.add_row("Raw Policy", spec.source.raw_policy)
            info_table.add_row("Actors", str(len(spec.actors)))
            info_table.add_row("Episodes", str(len(spec.episodes)))

            if spec.episodes:
                total_events = sum(len(ep.events) for ep in spec.episodes)
                info_table.add_row("Total Event Mappings", str(total_events))

            if spec.detect.rules:
                info_table.add_row("Detection Rules", str(len(spec.detect.rules)))
                info_table.add_row("Detection Min Score", str(spec.detect.min_score))

            console.print(info_table)

    raise typer.Exit(code=0)


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    dsl_app()
