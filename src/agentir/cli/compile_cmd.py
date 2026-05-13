"""agentir compile: one-shot pipeline (as -> opt -> llc)."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

app = typer.Typer(help="Compile: one-shot as -> opt -> llc pipeline.", rich_markup_mode="rich")

err_console = Console(stderr=True)


def _record_to_dict(record) -> dict:
    """Serialize an AgentIRRecord to a dict, filtering None values."""
    data = record.model_dump(mode="json")
    return {k: v for k, v in data.items() if v is not None}


@app.command()
def compile(
    frontend: Annotated[
        str | None, typer.Option("--frontend", help="Frontend parser name.")
    ] = None,
    hf_dataset: Annotated[
        str | None, typer.Option("--hf-dataset", help="Hugging Face dataset ID.")
    ] = None,
    input: Annotated[Path | None, typer.Option("--input", help="Local input file path.")] = None,
    split: Annotated[str, typer.Option("--split", help="Dataset split.")] = "train",
    limit: Annotated[int | None, typer.Option("--limit", help="Max records to process.")] = None,
    passes: Annotated[
        str | None, typer.Option("--passes", help="Comma-separated pass names.")
    ] = None,
    target: Annotated[str | None, typer.Option("--target", help="Target backend name.")] = None,
    output: Annotated[
        Path, typer.Option("--output", help="Final output file path.", show_default=False)
    ] = ...,  # type: ignore[assignment]
    workdir: Annotated[
        Path | None, typer.Option("--workdir", help="Working directory for intermediates.")
    ] = None,
    clean: Annotated[
        bool, typer.Option("--clean/--no-clean", help="Remove intermediate artifacts.")
    ] = False,
) -> None:
    """Run the full compilation pipeline: as -> opt -> llc."""
    from agentir.ir.record import AgentIRRecord

    console = Console()

    # Determine workdir
    if workdir is None:
        workdir = output.parent / ".agentir_compile"

    workdir.mkdir(parents=True, exist_ok=True)

    # Phase 1: agentir-as (parse source into raw IR)
    as_output: Path | None = None

    if frontend is not None and (hf_dataset is not None or input is not None):
        # Ensure frontends are imported
        import importlib

        for _mod in [
            "agentir.frontends.agenttrove",
            "agentir.frontends.claude_code",
            "agentir.frontends.codex_swebenchpro",
            "agentir.frontends.hermes_agent",
            "agentir.frontends.openhands",
            "agentir.frontends.sharegpt",
        ]:
            try:
                importlib.import_module(_mod)
            except Exception:
                pass

        from agentir.diagnostics.reporter import DiagnosticReporter
        from agentir.frontends.base import FrontendContext
        from agentir.frontends.registry import get_frontend, list_frontends
        from agentir.io.jsonl import write_jsonl as _write_jsonl

        fe = get_frontend(frontend)
        if fe is None:
            available = ", ".join(list_frontends()) or "(none)"
            err_console.print(
                f"[red]Error:[/red] Unknown frontend '{frontend}'. Available: {available}"
            )
            raise typer.Exit(code=3)

        as_output = workdir / "raw.air.jsonl"
        console.print(f"[bold]Phase 1: agentir-as[/bold] (frontend={frontend})")

        reporter = DiagnosticReporter()
        records_out: list[dict] = []

        if hf_dataset is not None:
            from agentir.io.hf import load_hf_dataset

            row_iter = load_hf_dataset(hf_dataset, split=split, streaming=True, limit=limit)
        elif input is not None:
            from agentir.io.jsonl import read_jsonl as _read_jsonl

            row_iter = _read_jsonl(input, limit=limit)
        else:
            err_console.print(
                "[red]Error:[/red] Must provide --input or --hf-dataset with --frontend."
            )
            raise typer.Exit(code=2)

        for row_idx, row in enumerate(row_iter):
            ctx = FrontendContext(
                dataset=hf_dataset,
                split=split,
                row_index=row_idx,
            )
            result = fe.parse_record(row, ctx)
            if result.diagnostics:
                reporter.add_all(result.diagnostics)
            if result.record is not None:
                records_out.append(_record_to_dict(result.record))

        _write_jsonl(as_output, iter(records_out))
        console.print(f"  Wrote {len(records_out)} records to {as_output}")

        if reporter.has_errors:
            reporter.print_summary()
            raise typer.Exit(code=1)
    elif input is not None:
        # No frontend specified; treat input as already-parsed IR
        as_output = input
        console.print(f"[bold]Phase 1: skipped[/bold] (using input directly: {input})")

    # Phase 2: agentir-opt (pass pipeline)
    opt_output: Path | None = as_output

    if passes is not None and as_output is not None:
        import importlib

        for _mod in [
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
        ]:
            try:
                importlib.import_module(_mod)
            except Exception:
                pass

        from agentir.diagnostics.reporter import DiagnosticReporter
        from agentir.io.jsonl import read_jsonl as _read_jsonl
        from agentir.io.jsonl import write_jsonl as _write_jsonl
        from agentir.passes.base import PassContext
        from agentir.passes.manager import PassManager
        from agentir.passes.registry import get_pass, list_passes

        pass_names = [p.strip() for p in passes.split(",") if p.strip()]
        if not pass_names:
            err_console.print("[red]Error:[/red] No passes specified.")
            raise typer.Exit(code=2)

        # Validate pass names
        for name in pass_names:
            if get_pass(name) is None:
                available = ", ".join(list_passes()) or "(none)"
                err_console.print(
                    f"[red]Error:[/red] Unknown pass '{name}'. Available: {available}"
                )
                raise typer.Exit(code=3)

        opt_output = workdir / "opt.air.jsonl"
        console.print(f"[bold]Phase 2: agentir-opt[/bold] (passes={', '.join(pass_names)})")

        ctx = PassContext()
        manager = PassManager()
        reporter = DiagnosticReporter()

        raw_records = list(_read_jsonl(as_output))
        out_records: list[dict] = []

        for raw in raw_records:
            record = AgentIRRecord.model_validate(raw)
            result = manager.run_pipeline(record, pass_names, ctx)
            reporter.add_all(result.diagnostics)
            out_records.append(_record_to_dict(result.record))

        _write_jsonl(opt_output, iter(out_records))
        console.print(f"  Wrote {len(out_records)} records to {opt_output}")

        if reporter.has_errors:
            reporter.print_summary()
            raise typer.Exit(code=1)
    else:
        console.print("[bold]Phase 2: skipped[/bold] (no passes specified)")

    # Phase 3: agentir-llc (lowering)
    if target is not None and opt_output is not None:
        import agentir.backends  # noqa: F401
        from agentir.backends.base import BackendContext
        from agentir.backends.registry import get_backend, list_backends
        from agentir.io.jsonl import read_jsonl as _read_jsonl
        from agentir.io.jsonl import write_jsonl as _write_jsonl

        console.print(f"[bold]Phase 3: agentir-llc[/bold] (target={target})")

        try:
            backend = get_backend(target)
        except KeyError as exc:
            available = ", ".join(list_backends()) or "(none)"
            err_console.print(f"[red]Error:[/red] {exc}. Available: {available}")
            raise typer.Exit(code=3)

        ctx = BackendContext()
        raw_records = list(_read_jsonl(opt_output))
        outputs: list[dict] = []

        for raw in raw_records:
            record = AgentIRRecord.model_validate(raw)
            result = backend.lower_record(record, ctx)
            outputs.append(result.output)

        # Infer final format
        suffix = output.suffix.lower()
        if suffix == ".parquet":
            from agentir.io.parquet import write_parquet as _write_parquet

            count = _write_parquet(output, outputs)
        else:
            count = _write_jsonl(output, iter(outputs))

        console.print(f"  Wrote {count} records to {output}")
    else:
        # No target -- just copy opt output to final output
        if opt_output is not None and opt_output != output:
            shutil.copy2(opt_output, output)
            console.print(f"  Copied to {output}")
        console.print("[bold]Phase 3: skipped[/bold] (no target specified)")

    # Cleanup
    if clean and workdir.exists():
        shutil.rmtree(workdir)
        console.print(f"  Cleaned up working directory: {workdir}")

    console.print()
    console.print("[bold green]Compile complete.[/bold green]")
