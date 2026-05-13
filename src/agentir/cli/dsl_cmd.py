"""CLI commands for the AgentIR Format DSL using Typer and Rich.

Provides subcommands for validating, probing, previewing, converting,
benchmarking, diffing, and initialising DSL format definition files.
"""

from __future__ import annotations

import json
import time
import sys
from pathlib import Path
from typing import Any, Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress
from rich.tree import Tree
from rich import box

from agentir.diagnostics.diagnostic import Diagnostic
from agentir.dsl.loader import load_dsl, validate_dsl
from agentir.dsl.compiler import compile_dsl_frontend
from agentir.dsl.models import TrajectoryFormat
from agentir.frontends.registry import list_frontends, detect_frontend
from agentir.frontends.base import FrontendContext
from agentir.ir.base import DiagnosticSeverity
from agentir.ir.record import AgentIRRecord


console = Console()
dsl_app = typer.Typer(name="dsl", help="DSL format definition commands")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_records(path: str, limit: Optional[int] = None) -> list[dict]:
    """Read JSON or JSONL records from *path*, up to *limit* rows.

    If the file has a ``.json`` extension (not ``.jsonl``) and the first
    line cannot be parsed as a standalone JSON object, the entire file is
    re-read as a JSON array or single object.
    """
    records: list[dict] = []
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            if limit and len(records) >= limit:
                break
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                if path.endswith(".json") and not path.endswith(".jsonl"):
                    f.seek(0)
                    data = json.load(f)
                    if isinstance(data, list):
                        records.extend(data[:limit])
                    else:
                        records.append(data)
                    break
                continue
    return records


def _build_field_tree(
    records: list[dict], tree: Tree, prefix: str = ""
) -> None:
    """Recursively add field information to a Rich Tree."""
    if not records:
        return

    keys_info: dict[str, tuple[str, Any]] = {}
    for rec in records:
        if not isinstance(rec, dict):
            continue
        for k, v in rec.items():
            if k not in keys_info:
                val_type = type(v).__name__
                keys_info[k] = (val_type, v)

    for key in sorted(keys_info.keys()):
        typ, sample = keys_info[key]
        sample_str = repr(sample)
        if len(sample_str) > 60:
            sample_str = sample_str[:57] + "..."
        label = (
            f"[bold cyan]{key}[/bold cyan] "
            f"[dim]({typ})[/dim] "
            f"[green]{sample_str}[/green]"
        )

        sub_records: list[dict] = []
        for rec in records:
            if isinstance(rec, dict) and key in rec:
                val = rec[key]
                if isinstance(val, dict):
                    sub_records.append(val)
                elif isinstance(val, list):
                    for item in val:
                        if isinstance(item, dict):
                            sub_records.append(item)

        if sub_records:
            branch = tree.add(label)
            _build_field_tree(sub_records, branch)
        else:
            tree.add(label)


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


@dsl_app.command()
def validate(dsl_file: str) -> None:
    """Validate a .agentir.yaml DSL file and report diagnostics."""
    try:
        ok, diagnostics = validate_dsl(dsl_file)
    except Exception as exc:
        console.print(
            Panel(
                f"[bold red][FAIL][/bold red] {exc}",
                title="Validation Error",
                border_style="red",
            )
        )
        raise typer.Exit(1)

    if ok:
        console.print(
            Panel(
                "[bold green][PASS][/bold green] DSL is valid.",
                title=Path(dsl_file).name,
                border_style="green",
            )
        )
    else:
        console.print(
            Panel(
                "[bold red][FAIL][/bold red] DSL has errors.",
                title=Path(dsl_file).name,
                border_style="red",
            )
        )

    if diagnostics:
        table = Table(title="Diagnostics", box=box.ROUNDED)
        table.add_column("Severity", style="bold")
        table.add_column("Code")
        table.add_column("Message")

        sev_icons = {
            DiagnosticSeverity.INFO: "[dim]INFO [/dim]",
            DiagnosticSeverity.WARNING: "[yellow]WARN [/yellow]",
            DiagnosticSeverity.ERROR: "[red]ERROR[/red]",
            DiagnosticSeverity.FATAL: "[bold red]FATAL[/bold red]",
        }

        for diag in diagnostics:
            icon = sev_icons.get(diag.severity, diag.severity.value)
            table.add_row(icon, diag.code, diag.message)

        console.print(table)

    raise typer.Exit(0 if ok else 1)


@dsl_app.command()
def probe(
    input_path: str,
    dsl_file: Optional[str] = typer.Option(
        None, "--dsl", "-d", help="Optional DSL file for detection scoring"
    ),
) -> None:
    """Inspect the first few records from an input file.

    Shows field structure as a tree and optionally checks detection scores
    against a DSL file.
    """
    records = _read_records(input_path, limit=5)

    if not records:
        console.print("[bold red]No records found in input file.[/bold red]")
        raise typer.Exit(1)

    console.print(
        f"[bold]Read {len(records)} record(s) from[/bold] [cyan]{input_path}[/cyan]\n"
    )

    tree = Tree(f"[bold]Fields in {Path(input_path).name}[/bold]")
    _build_field_tree(records, tree)
    console.print(tree)

    if dsl_file:
        console.print()
        table = Table(
            title=f"Detection Scores ({Path(dsl_file).name})",
            box=box.ROUNDED,
        )
        table.add_column("#", style="dim")
        table.add_column("Record Key", style="cyan")
        table.add_column("Detection", style="green")

        for i, rec in enumerate(records, 1):
            sample_key = (
                rec.get("id")
                or rec.get("instance_id")
                or rec.get("trajectory_id")
                or rec.get("conversation_id")
                or f"record-{i}"
            )
            scores = detect_frontend(rec)
            score_lines = ", ".join(
                f"{name}: {score:.2f}" for name, score in scores
            )
            table.add_row(str(i), str(sample_key), score_lines)

        console.print(table)


@dsl_app.command()
def preview(
    dsl_file: str,
    input_path: str,
    limit: int = typer.Option(
        5, "--limit", "-n", help="Number of records to preview"
    ),
    show_events: bool = typer.Option(
        False, "--events", "-e", help="Show event details"
    ),
) -> None:
    """Preview conversion of input records using a DSL file.

    Loads the DSL, reads a limited number of records, converts each one
    through the runtime frontend, and displays the resulting event counts
    and types.
    """
    try:
        spec = load_dsl(dsl_file)
    except Exception as exc:
        console.print(f"[bold red]Error loading DSL:[/bold red] {exc}")
        raise typer.Exit(1)

    frontend = compile_dsl_frontend(spec, dsl_path=dsl_file)

    records = _read_records(input_path, limit=limit)
    if not records:
        console.print("[bold red]No records read from input.[/bold red]")
        raise typer.Exit(1)

    console.print(
        f"[bold]Preview:[/bold] [cyan]{Path(dsl_file).name}[/cyan] "
        f"on [cyan]{Path(input_path).name}[/cyan] "
        f"({len(records)} record(s))\n"
    )

    for i, rec in enumerate(records, 1):
        ctx = FrontendContext(
            dataset=Path(input_path).stem,
            row_index=i - 1,
        )
        result = frontend.parse_record(rec, ctx)

        if result.record is None:
            console.print(f"  [dim]{i}.[/dim] [red]Conversion failed[/red]")
            continue

        air = result.record
        record_id = air.record_id

        total_events = sum(len(ep.events) for ep in air.episodes)

        event_type_counts: dict[str, int] = {}
        for ep in air.episodes:
            for evt in ep.events:
                etype = evt.event_type.value
                event_type_counts[etype] = event_type_counts.get(etype, 0) + 1

        type_summary = ", ".join(
            f"{t}: {c}" for t, c in sorted(event_type_counts.items())
        )

        console.print(
            f"  [bold cyan]{i}.[/bold cyan] [green]{record_id}[/green] "
            f"[dim]|[/dim] [bold]{total_events} event(s)[/bold] "
            f"[dim]({type_summary})[/dim]"
        )

        if show_events:
            evt_table = Table(
                title=f"Events for {record_id}",
                box=box.SIMPLE,
                show_header=True,
            )
            evt_table.add_column("Idx", style="dim", width=4)
            evt_table.add_column("Event ID", style="cyan", width=24)
            evt_table.add_column("Type", style="magenta", width=22)
            evt_table.add_column("Role", style="blue", width=12)
            evt_table.add_column("Content Preview", style="green", width=50)

            for ep in air.episodes:
                for evt in ep.events:
                    content_preview = ""
                    if evt.content:
                        first_block = evt.content[0]
                        cp = getattr(first_block, "text", None) or str(
                            getattr(first_block, "data", first_block)
                        )
                        if len(cp) > 50:
                            content_preview = cp[:47] + "..."
                        else:
                            content_preview = cp

                    evt_table.add_row(
                        str(evt.idx),
                        evt.event_id[:24],
                        evt.event_type.value[:22],
                        (evt.role.value if evt.role else "-"),
                        content_preview[:60],
                    )

            console.print(evt_table)
            console.print()

    total_diags = 0
    error_diags = 0
    for rec in records:
        ctx_i = FrontendContext(
            dataset=Path(input_path).stem,
            row_index=0,
        )
        result_i = frontend.parse_record(rec, ctx_i)
        if result_i.record:
            total_diags += len(result_i.record.diagnostics)
            error_diags += sum(
                1
                for d in result_i.record.diagnostics
                if d.severity in (DiagnosticSeverity.ERROR, DiagnosticSeverity.FATAL)
            )

    if total_diags:
        console.print(
            f"[dim]{total_diags} diagnostic(s) ({error_diags} error(s))[/dim]"
        )


@dsl_app.command()
def convert(
    dsl_file: str,
    input_path: str,
    output_path: str = typer.Option(
        "out.air.jsonl", "--output", "-o", help="Output file path"
    ),
) -> None:
    """Full conversion of input records to AgentIR JSONL using a DSL file.

    Reads all records, converts through the runtime frontend, and writes
    AgentIR JSONL to the output path.
    """
    try:
        spec = load_dsl(dsl_file)
    except Exception as exc:
        console.print(f"[bold red]Error loading DSL:[/bold red] {exc}")
        raise typer.Exit(1)

    frontend = compile_dsl_frontend(spec, dsl_path=dsl_file)

    records = _read_records(input_path)
    if not records:
        console.print("[bold red]No records found in input.[/bold red]")
        raise typer.Exit(1)

    total_records = len(records)
    total_events = 0
    failures = 0
    start_time = time.perf_counter()

    with Progress() as progress:
        task = progress.add_task("[cyan]Converting...", total=total_records)

        with open(output_path, "w", encoding="utf-8") as outf:
            for i, rec in enumerate(records):
                ctx = FrontendContext(
                    dataset=Path(input_path).stem,
                    row_index=i,
                )
                result = frontend.parse_record(rec, ctx)

                if result.record is None:
                    failures += 1
                    progress.advance(task)
                    continue

                air_dict = result.record.model_dump(
                    mode="json", exclude_none=False
                )
                outf.write(json.dumps(air_dict, default=str) + "\n")

                total_events += sum(
                    len(ep.events) for ep in result.record.episodes
                )
                progress.advance(task)

    elapsed = time.perf_counter() - start_time
    rate = total_records / elapsed if elapsed > 0 else float("inf")

    console.print(
        Panel.fit(
            f"[bold green]{total_records}[/bold green] records, "
            f"[bold green]{total_events}[/bold green] events, "
            f"[bold red]{failures}[/bold red] failures\n"
            f"[bold]{elapsed:.2f}s[/bold] | "
            f"[bold cyan]{rate:.1f} records/s[/bold cyan]",
            title="Conversion Complete",
            border_style="green",
        )
    )


@dsl_app.command()
def bench(
    dsl_file: str,
    input_path: str,
    limit: Optional[int] = typer.Option(
        None, "--limit", "-n", help="Max records to benchmark"
    ),
) -> None:
    """Benchmark conversion speed using a DSL file on input records."""
    try:
        spec = load_dsl(dsl_file)
    except Exception as exc:
        console.print(f"[bold red]Error loading DSL:[/bold red] {exc}")
        raise typer.Exit(1)

    frontend = compile_dsl_frontend(spec, dsl_path=dsl_file)

    records = _read_records(input_path, limit=limit)
    if not records:
        console.print("[bold red]No records found.[/bold red]")
        raise typer.Exit(1)

    total_records = len(records)
    total_events = 0
    total_output_size = 0
    start_time = time.perf_counter()

    for i, rec in enumerate(records):
        ctx = FrontendContext(
            dataset=Path(input_path).stem,
            row_index=i,
        )
        result = frontend.parse_record(rec, ctx)
        if result.record is not None:
            total_events += sum(
                len(ep.events) for ep in result.record.episodes
            )
            total_output_size += sys.getsizeof(
                result.record.model_dump()
            )

    elapsed = time.perf_counter() - start_time

    records_per_sec = total_records / elapsed if elapsed > 0 else float("inf")
    events_per_sec = total_events / elapsed if elapsed > 0 else float("inf")

    console.print(
        Panel.fit(
            f"[bold]{total_records}[/bold] records, "
            f"[bold]{total_events}[/bold] events in "
            f"[bold cyan]{elapsed:.3f}s[/bold cyan]\n\n"
            f"[bold green]{records_per_sec:.1f} records/s[/bold green]  |  "
            f"[bold green]{events_per_sec:.1f} events/s[/bold green]\n"
            f"Est. output size: "
            f"[dim]{total_output_size / 1024:.1f} KiB[/dim]",
            title="Benchmark Results",
            border_style="cyan",
        )
    )


@dsl_app.command()
def diff(
    dsl_file_a: str,
    dsl_file_b: str,
    input_path: str,
) -> None:
    """Compare two DSL files by converting the same input records.

    Shows differences in event counts, event types, and output structure.
    """
    try:
        spec_a = load_dsl(dsl_file_a)
        spec_b = load_dsl(dsl_file_b)
    except Exception as exc:
        console.print(f"[bold red]Error loading DSL:[/bold red] {exc}")
        raise typer.Exit(1)

    frontend_a = compile_dsl_frontend(spec_a, dsl_path=dsl_file_a)
    frontend_b = compile_dsl_frontend(spec_b, dsl_path=dsl_file_b)

    records = _read_records(input_path, limit=10)
    if not records:
        console.print("[bold red]No records found.[/bold red]")
        raise typer.Exit(1)

    name_a = Path(dsl_file_a).name
    name_b = Path(dsl_file_b).name

    table = Table(
        title=f"DSL Diff: {name_a} vs {name_b}",
        box=box.ROUNDED,
    )
    table.add_column("Record", style="dim")
    table.add_column(f"Events ({name_a})", justify="right")
    table.add_column(f"Events ({name_b})", justify="right")
    table.add_column("Delta", justify="right")
    table.add_column("Unique Types", style="yellow")

    for i, rec in enumerate(records, 1):
        ctx = FrontendContext(
            dataset=Path(input_path).stem,
            row_index=i - 1,
        )
        ra = frontend_a.parse_record(rec, ctx)
        rb = frontend_b.parse_record(rec, ctx)

        count_a = (
            sum(len(ep.events) for ep in ra.record.episodes)
            if ra.record
            else 0
        )
        count_b = (
            sum(len(ep.events) for ep in rb.record.episodes)
            if rb.record
            else 0
        )
        delta_val = count_b - count_a
        if delta_val > 0:
            delta_str = f"[green]+{delta_val}[/green]"
        elif delta_val < 0:
            delta_str = f"[red]{delta_val}[/red]"
        else:
            delta_str = "[dim]0[/dim]"

        types_a: set[str] = set()
        types_b: set[str] = set()
        if ra.record:
            for ep in ra.record.episodes:
                for evt in ep.events:
                    types_a.add(evt.event_type.value)
        if rb.record:
            for ep in rb.record.episodes:
                for evt in ep.events:
                    types_b.add(evt.event_type.value)

        only_a = types_a - types_b
        only_b = types_b - types_a
        unique_parts: list[str] = []
        if only_a:
            unique_parts.append(
                f"[red]only-A: {', '.join(sorted(only_a))}[/red]"
            )
        if only_b:
            unique_parts.append(
                f"[green]only-B: {', '.join(sorted(only_b))}[/green]"
            )
        unique_str = (
            "\n".join(unique_parts) if unique_parts else "[dim]same[/dim]"
        )

        if ra.record:
            row_id = ra.record.record_id
        elif rb.record:
            row_id = rb.record.record_id
        else:
            row_id = f"record-{i}"

        table.add_row(
            f"[cyan]{row_id}[/cyan]",
            str(count_a),
            str(count_b),
            delta_str,
            unique_str,
        )

    console.print(table)


# ---------------------------------------------------------------------------
# DSL template strings
# ---------------------------------------------------------------------------


_MINIMAL_SHAREGPT_TEMPLATE = '# {{title}}\n# Generated by: agentir dsl init --template minimal-sharegpt\n#\n# This template defines a format for ShareGPT-style conversation data.\n# Customise the field paths, transforms, and detection rules below.\n# ---------------------------------------------------------------------------\n\napiVersion: agentir.qitor.ai/v0.1\nkind: TrajectoryFormat\nmetadata:\n  name: {{format_name}}\n  description: "Minimal ShareGPT format -- define your conversation structure here."\n  version: "0.1.0"\n  author: "your-name"\n\n# --- Detection rules ---------------------------------------------------------\ndetect:\n  rules:\n    # Adjust the field checks and scores to match your data.\n    - field_exists: $.conversations\n      score: 0.5\n    - field_is_list: $.conversations\n      score: 0.3\n\n# --- Source metadata ---------------------------------------------------------\nsource:\n  framework: "sharegpt"\n  format: "jsonl"\n  default_dataset: "your-dataset-name"\n\n# --- Top-level variables ------------------------------------------------------\nvars: {{}}\n\n# --- Source-field overrides --------------------------------------------------\n# source_overrides:\n#   row_id: {{path: "$.id"}}\n\n# --- Task specification ------------------------------------------------------\ntask:\n  instruction: {{path: "$.instruction"}}\n  # category: {{const: "conversation"}}\n\n# --- Episodes ----------------------------------------------------------------\nepisodes:\n  - episode_id: {{template: "{{{{record_id}}}}"}}\n    task_id: {{template: "{{{{record_id}}}}"}}\n    events:\n\n      # -- System prompt (if present) ----------------------------------------\n      - foreach: {{path: "$.system_prompt_text"}}\n        as: system_text\n        emit:\n          event_id: {{template: "{{{{record_id}}}}-system"}}\n          idx: 0\n          event_type: {{const: "system_message"}}\n          role: {{const: "system"}}\n          content: {{template: "{{{{system_text}}}}"}}\n\n      # -- Conversation turns ------------------------------------------------\n      - foreach: {{path: "$.conversations"}}\n        as: turn\n        index_as: turn_idx\n        emit:\n          event_id: {{template: "{{{{record_id}}}}-turn-{{{{turn_idx}}}}"}}\n          idx: {{var: turn_idx}}\n          event_type: {{transform: "role_to_event_type", input: {{path: "$.turn.from"}}}}\n          role: {{transform: "role_to_message_role", input: {{path: "$.turn.from"}}}}\n          content: {{path: "$.turn.value"}}\n\n# --- Outcome (optional) ------------------------------------------------------\n# outcome:\n#   status: {{path: "$.status"}}\n#   passed: {{path: "$.passed"}}'


_NATIVE_TOOL_JSONL_TEMPLATE = '# {{title}}\n# Generated by: agentir dsl init --template native-tool-jsonl\n#\n# This template is for datasets that use native tool-call structures\n# (e.g. OpenAI-style messages with tool_calls / tool role responses).\n# ---------------------------------------------------------------------------\n\napiVersion: agentir.qitor.ai/v0.1\nkind: TrajectoryFormat\nmetadata:\n  name: {{format_name}}\n  description: "Native tool-call JSONL format."\n  version: "0.1.0"\n  author: "your-name"\n\n# --- Detection rules ---------------------------------------------------------\ndetect:\n  rules:\n    - field_exists: $.messages\n      score: 0.7\n    - field_is_list: $.messages\n      score: 0.3\n\n# --- Source metadata ---------------------------------------------------------\nsource:\n  framework: "openai"\n  format: "jsonl"\n  default_dataset: "your-dataset-name"\n\n# --- Top-level variables ------------------------------------------------------\nvars: {{}}\n\n# --- Source-field overrides --------------------------------------------------\n# source_overrides:\n#   row_id: {{path: "$.id"}}\n\n# --- Task specification ------------------------------------------------------\ntask:\n  instruction:\n    first_of:\n      - {{path: "$.messages[0].content"}}\n      - {{path: "$.instruction"}}\n\n# --- Tool registry (if tools are defined per-record) -------------------------\n# tool_registry:\n#   from: {{path: "$.tools"}}\n#   item:\n#     name: {{path: "$.item.function.name"}}\n#     description: {{path: "$.item.function.description"}}\n#     input_schema: {{path: "$.item.function.parameters"}}\n\n# --- Episodes ----------------------------------------------------------------\nepisodes:\n  - episode_id: {{template: "{{{{record_id}}}}"}}\n    task_id: {{template: "{{{{record_id}}}}"}}\n    events:\n      - foreach: {{path: "$.messages"}}\n        as: msg\n        index_as: msg_idx\n        emit:\n          event_id: {{template: "{{{{record_id}}}}-msg-{{{{msg_idx}}}}"}}\n          idx: {{var: msg_idx}}\n          event_type: {{transform: "role_to_event_type", input: {{path: "$.msg.role"}}}}\n          role: {{transform: "role_to_message_role", input: {{path: "$.msg.role"}}}}\n          content: {{path: "$.msg.content"}}\n          # If the message contains tool_calls, the content block will\n          # encode them. You can also use the `action` field to emit\n          # dedicated TOOL_CALL / TOOL_RESULT events.\n          action:\n            kind: {{const: "generic_tool"}}\n            tool_call_id: {{path: "$.msg.tool_call_id"}}\n            tool_name: {{path: "$.msg.name"}}\n\n# --- Outcome (optional) ------------------------------------------------------\n# outcome:\n#   status: {{path: "$.status"}}\n#   passed: {{path: "$.success"}}'


@dsl_app.command()
def init(
    template: str = typer.Option(
        "minimal-sharegpt",
        "--template",
        "-t",
        help="Template name (minimal-sharegpt, native-tool-jsonl)",
    ),
    output: str = typer.Option(
        "my_format.agentir.yaml",
        "--output",
        "-o",
        help="Output file path for the new DSL file",
    ),
) -> None:
    """Create a new DSL template file with placeholder comments.

    Use --template to pick from the available starting points:
    minimal-sharegpt, native-tool-jsonl.
    """
    template_map = {
        "minimal-sharegpt": _MINIMAL_SHAREGPT_TEMPLATE,
        "native-tool-jsonl": _NATIVE_TOOL_JSONL_TEMPLATE,
    }

    if template not in template_map:
        console.print(
            f"[bold red]Unknown template:[/bold red] {template}\n"
            f"Supported templates: "
            f"{', '.join(sorted(template_map.keys()))}"
        )
        raise typer.Exit(1)

    out_path = Path(output)
    if out_path.exists():
        console.print(
            f"[bold yellow]Warning:[/bold yellow] {out_path} already exists. "
            "Use -o to specify a different path."
        )
        raise typer.Exit(1)

    format_name = out_path.stem.replace(".agentir", "")

    template_str = template_map[template]
    filled = template_str.format(
        title=f"AgentIR DSL: {format_name}",
        format_name=format_name,
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(filled + "\n", encoding="utf-8")

    console.print(
        Panel(
            f"[bold green]Created[/bold green] [cyan]{output}[/cyan]\n"
            f"Template: [bold]{template}[/bold]\n\n"
            "Edit the file to customise field paths, detection rules,\n"
            "and mappings for your dataset.",
            title="DSL Initialised",
            border_style="green",
        )
    )
