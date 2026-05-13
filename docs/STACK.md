# Technology Stack

## Decision

Use a **Python-first stack** for v0.1.

Python is the correct first implementation language because agent trajectory datasets are currently distributed primarily through Hugging Face Datasets, JSON/JSONL, and Parquet; training pipelines expect Python; and schema/validation tooling is mature. Rust can be introduced later for hot paths such as streaming parsers, Parquet scanning, and diff normalization, but v0.1 must prioritize correctness, extensibility, and ecosystem fit.

## Runtime and package management

- Python: `>=3.11,<3.14`
- Package manager: `uv`
- Build backend: `hatchling`
- Package name: `agentir`
- License: Apache-2.0
- CLI entrypoints:
  - `agentir`
  - `agentir-as`
  - `agentir-opt`
  - `agentir-llc`

## Core dependencies

```toml
[project]
dependencies = [
  "pydantic>=2.8",
  "typer>=0.12",
  "rich>=13.7",
  "orjson>=3.10",
  "jsonlines>=4.0",
  "datasets>=2.20",
  "huggingface-hub>=0.24",
  "pyarrow>=16.0",
  "pandas>=2.2",
  "typing-extensions>=4.12",
  "defusedxml>=0.7",
  "unidiff>=0.7",
]
```

## Optional dependencies

```toml
[project.optional-dependencies]
dev = [
  "pytest>=8.2",
  "pytest-cov>=5.0",
  "hypothesis>=6.100",
  "mypy>=1.10",
  "ruff>=0.5",
  "pre-commit>=3.7",
]
docs = [
  "mkdocs>=1.6",
  "mkdocs-material>=9.5",
]
perf = [
  "duckdb>=1.0",
  "ijson>=3.3",
]
otel = [
  "opentelemetry-api>=1.25",
  "opentelemetry-sdk>=1.25",
]
```

## Why these choices

### Pydantic v2

Use Pydantic v2 for all public IR models. It gives typed validation, serialization, strict/lax modes, and automatic JSON Schema generation. The implementation must expose generated schema files under `schema/`.

### Typer + Rich

Use Typer for CLI because it is Python type-hint friendly and built on Click. Use Rich for readable compiler-style errors, tables, and progress output.

### Hugging Face Datasets + PyArrow

Use Hugging Face Datasets for loading public datasets and streaming large sources. Use PyArrow/Parquet as the preferred large-scale storage backend. JSONL is acceptable for small examples and debugging; Parquet must be supported for large corpora.

### Ruff + mypy + pytest

Use Ruff for formatting/linting, mypy for static typing, and pytest for unit, regression, and roundtrip tests.

## Storage formats

| Extension | Purpose |
|---|---|
| `.raw.air.jsonl` | RawIR JSONL, lossless source-preserving records |
| `.parsed.air.jsonl` | ParsedIR JSONL, best-effort event extraction |
| `.canonical.air.jsonl` | Canonical AgentIR JSONL, verifier-passable records |
| `.air.parquet` | Large-scale AgentIR dataset |
| `.airpack` | Future bundle format containing IR + artifacts + reports |
| `.loss.md` | Lowering loss report |
| `.verify.md` | Verifier report |

## Performance posture for v0.1

The v0.1 implementation must be streaming-safe:

- No command may require loading an entire dataset into memory.
- Every frontend must accept `--limit` and `--streaming`.
- JSONL readers/writers must process one record at a time.
- Parquet writers may buffer batches but must expose `--batch-size`.
- Passes must support iterator-style processing whenever possible.

## Future Rust layer

Do not implement Rust in v0.1. Reserve it for v0.3+ if profiling shows bottlenecks in:

- XML/tool-block parsing
- JSONL streaming
- diff normalization
- source-map generation
- Parquet conversion

