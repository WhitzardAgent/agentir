# AgentIR Quickstart Guide

## What is AgentIR?

AgentIR is a **compiler infrastructure for agentic trajectories**. It provides:
- A **canonical intermediate representation (IR)** for LLM agent conversations,
  tool calls, code edits, and environment interactions.
- A **declarative DSL** (`*.agentir.yaml`) for mapping any trajectory format
  into the IR without writing parser code.
- A **composable pass pipeline** for normalization, canonicalization,
  verification, and training-data slicing.

Think of it as "LLVM/MLIR, but for agent trajectories."

## Installation

```bash
# Clone and install
git clone <repo-url> agentir && cd agentir
uv sync                                  # Installs all dependencies
pip install -e .                         # Editable install (alternative)
```

The CLI is available as `agentir` after installation:
```bash
agentir --help
```

## Basic Concepts

| Concept | Description |
|---------|-------------|
| **AgentIR Record** | The canonical IR unit: an `AgentIRRecord` has episodes, events, content blocks, and provenance. |
| **DSL Format** | A `*.agentir.yaml` file declaring how to parse a data source into AgentIR records. No code needed. |
| **Frontend** | The runtime parser compiled from a DSL spec. It implements `BaseFrontend.detect()` and `parse_record()`. |
| **Pass** | A single transformation or check on AgentIR records (e.g., `parse-sharegpt`, `canonicalize-tools`, `verify`). |
| **Pass Pipeline** | An ordered sequence of passes composed into an optimization/normalization pipeline. |
| **IR Levels** | `PARSED` (fresh from frontend), `CANONICALIZED` (after passes), `OPTIMIZED` (training-ready). |

## 5-Minute Quickstart

We will walk through exploring a trajectory format using the CLI.

### 1. Validate a DSL definition

```bash
agentir dsl validate dsl/formats/openhands.agentir.yaml
```

This checks that the YAML file is well-formed, has all required fields, and
passes Pydantic schema validation.  It prints a `PASS` or `FAIL` panel
with any diagnostics.

### 2. Probe your data

```bash
# Create a small sample file first, or use any JSONL file.
agentir dsl probe examples/end_to_end/sample_data.jsonl \
    --dsl examples/end_to_end/sample_data.jsonl -n 5
```

**Without `--dsl`** it shows the field tree (paths, types, sample values).
**With `--dsl`** it also runs detection scoring  how well the DSL
recognizes each record -- with a verdict (`MATCH` / `LOW`).

### 3. Preview conversion

```bash
agentir dsl preview dsl/formats/openhands.agentir.yaml \
    tests/fixtures/openhands_sample.jsonl -n 2 --show-events
```

Prints a summary table (Record ID, event count, event types, roles) and
optional event detail cards with content previews.  This lets you verify
the DSL mapping is correct before a full conversion.

### 4. Full conversion

```bash
agentir dsl convert dsl/formats/openhands.agentir.yaml \
    tests/fixtures/openhands_sample.jsonl --output out.air.jsonl
```

Converts every source record into AgentIR JSONL and writes it to
`out.air.jsonl`.  A statistics table shows records processed, events
emitted, and throughput.

## Creating a Custom DSL Format

Use the interactive template generator:

```bash
agentir dsl init my-project.agentir.yaml \
    --name my-project \
    --title "My Project Trajectories" \
    --framework custom
```

This creates a scaffold you can edit.  The key sections to fill in:

1. **`detect.rules`** -- field-existence/list checks that identify your format.
2. **`episodes[0].events`** -- `foreach` over your conversation array, mapping
   `role`, `content`, and `event_type` with transforms like
   `role_to_event_type`.
3. **`passes.default`** -- which passes to run (use `parse-sharegpt` for chat,
   or the new pass name if you register a custom one).

Validate, iterate: `validate` -> `probe` -> `preview` -> `convert`.

## Key Files

| File | Purpose |
|------|---------|
| `dsl/formats/*.agentir.yaml` | Built-in DSL format definitions (OpenHands, Claude Code, etc.) |
| `src/agentir/dsl/compiler.py` | `RuntimeDSLFrontend`: evaluates DSL specs at runtime |
| `src/agentir/dsl/models.py` | Pydantic models for the DSL schema |
| `src/agentir/passes/manager.py` | `PassManager`: orchestrates the pass pipeline |
| `src/agentir/ir/record.py` | `AgentIRRecord`: the top-level IR model |
| `src/agentir/cli/dsl_cmd.py` | `agentir dsl` subcommands (validate, probe, preview, convert) |
| `examples/end_to_end/` | Runnable end-to-end workflow example |
| `docs/DSL.md` | Full DSL reference |
| `docs/PASSES.md` | Pass pipeline documentation |
| `docs/SPEC.md` | IR specification |

## Next Steps

- Run the end-to-end example: `PYTHONPATH=src uv run python examples/end_to_end/workflow.py`
- Read the full [DSL reference](docs/DSL.md)
- Explore pass development in [PASSES.md](docs/PASSES.md)
- Check the [project roadmap](docs/ROADMAP.md) for upcoming features
