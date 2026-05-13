"""agentir schema export: export JSON Schema from Pydantic models."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

app = typer.Typer(help="Schema export commands.", rich_markup_mode="rich")


@app.command()
def export(
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Output JSON Schema file path.")
    ] = None,
) -> None:
    """Export JSON Schema from the AgentIR Pydantic model."""
    console = Console()

    from agentir.ir.record import AgentIRRecord

    schema = AgentIRRecord.model_json_schema(mode="serialization")
    schema_str = json.dumps(schema, indent=2, ensure_ascii=False)

    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(schema_str + "\n")
        console.print(f"[bold green]Schema exported to[/bold green] {output}")
    else:
        console.print(schema_str)
