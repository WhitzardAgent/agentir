# Claude Code Master Prompt for agentir v0.1

You are Claude Code working in a fresh repository named `agentir`.

Your job is implementation only. Do not redesign the architecture. Follow the documents in this package exactly:

- `README.md`
- `docs/STACK.md`
- `docs/DESIGN.md`
- `docs/SPEC.md`
- `docs/DIALECTS.md`
- `docs/PASSES.md`
- `docs/FRONTENDS.md`
- `docs/BACKENDS.md`
- `docs/CLI.md`
- `docs/DIAGNOSTICS.md`
- `docs/TESTING.md`
- `docs/ROADMAP.md`
- `docs/PROJECT_STRUCTURE.md`

## Mission

Build `agentir` v0.1: a Python-first compiler infrastructure for agentic trajectories.

It must parse heterogeneous agent traces into AgentIR, run pass pipelines, verify them, and lower to target training/framework formats with explicit diagnostics and loss reports.

## Hard constraints

1. Use Python `>=3.11,<3.14`.
2. Use Pydantic v2 for all IR models.
3. Use Typer + Rich for CLI.
4. Use Hugging Face Datasets and PyArrow for dataset loading/storage.
5. Use Ruff, mypy, and pytest.
6. Implement compiler-style commands:
   - `agentir-as`
   - `agentir-opt`
   - `agentir-llc`
   - `agentir verify`
   - `agentir schema export`
   - `agentir compile`
7. Preserve raw source rows in every frontend.
8. Every parsed event must include provenance when possible.
9. Every backend must return a `LossReport`.
10. Do not call external LLM APIs.
11. Do not implement Rust in v0.1.
12. Do not silently drop reasoning; apply reasoning policy.
13. Do not silently drop tool semantics; report lowering loss.

## Implementation phases

### Phase 0: Repository setup

Create the exact structure specified in `docs/PROJECT_STRUCTURE.md`.

Create:

- `pyproject.toml` based on `pyproject.template.toml`
- `LICENSE` with Apache-2.0
- `.gitignore`
- `.pre-commit-config.yaml`
- `src/agentir/version.py`
- package `__init__.py` files

Run:

```bash
uv sync --extra dev
uv run ruff format .
uv run ruff check .
uv run pytest
```

### Phase 1: IR models

Implement all Pydantic models from `docs/SPEC.md` under `src/agentir/ir/`.

Requirements:

- Use `model_config = ConfigDict(extra="allow")` only where appropriate.
- Prefer strict enums for public schema fields.
- Implement JSON serialization helpers.
- Implement `agentir schema export --output schema/agentir.schema.v0.1.json`.

Acceptance:

- `tests/test_ir_models.py` passes.
- JSON schema export works.

### Phase 2: Diagnostics and IO

Implement:

- `src/agentir/diagnostics/diagnostic.py`
- `src/agentir/diagnostics/reporter.py`
- `src/agentir/io/jsonl.py`
- `src/agentir/io/parquet.py`
- `src/agentir/io/hf.py`

Acceptance:

- Read/write JSONL one record at a time.
- Basic Parquet read/write works.
- Diagnostic rendering matches compiler-style examples.

### Phase 3: Frontend framework

Implement frontend base classes and registry.

Implement frontends:

1. `agenttrove`
2. `codex-swebenchpro`
3. `claude-code`
4. `openhands`
5. `hermes-agent`

Follow `docs/FRONTENDS.md` exactly.

If live Hugging Face loading is unavailable, tests must use synthetic fixtures under `tests/fixtures/`.

Acceptance:

- `agentir-as --frontend <name> --input tests/fixtures/<name>_sample.jsonl --output out.raw.air.jsonl` works for all five.
- Frontends preserve raw rows.
- Frontends emit events and source fields.

### Phase 4: Pass manager and passes

Implement:

- pass base classes
- registry
- manager
- required passes in `docs/PASSES.md`

Required passes:

- `parse-sharegpt`
- `parse-hermes-xml`
- `parse-claude-log`
- `parse-openhands-tool-calls`
- `canonicalize-tools`
- `pair-tool-results`
- `extract-patches`
- `normalize-outcome`
- `redact-reasoning`
- `slice-training`
- `verify`

Acceptance:

```bash
agentir-opt out/hermes.raw.air.jsonl \
  --passes parse-hermes-xml,canonicalize-tools,pair-tool-results,normalize-outcome,verify \
  --output out/hermes.canonical.air.jsonl
```

must work on fixture data.

### Phase 5: Backends

Implement backend base classes, registry, loss reports, and required backends:

- `sft`
- `process-supervision`
- `openai-tools`
- `hermes-xml`
- `openhands`
- `sharegpt`

Follow `docs/BACKENDS.md` exactly.

Acceptance:

```bash
agentir-llc out/hermes.canonical.air.jsonl --target sft --output out/hermes.sft.jsonl --loss-report out/hermes.loss.md
```

works and emits a markdown loss report.

### Phase 6: CLI integration

Implement all CLI commands from `docs/CLI.md`:

- `agentir-as`
- `agentir-opt`
- `agentir-llc`
- `agentir verify`
- `agentir schema export`
- `agentir compile`

Requirements:

- Rich summaries.
- Streaming record processing.
- Correct exit codes.
- Useful help text.

### Phase 7: Tests and quality gates

Implement all tests from `docs/TESTING.md`.

Run:

```bash
uv run ruff format .
uv run ruff check .
uv run mypy src
uv run pytest --cov=agentir --cov-report=term-missing
```

Fix all failures.

## Completion criteria

The implementation is complete only when:

1. All required commands run on fixture data.
2. All five frontends parse fixture records.
3. Required passes work.
4. Required backends work.
5. Loss reports are produced.
6. JSON Schema export works.
7. Tests pass.
8. Ruff passes.
9. mypy passes for at least `src/agentir/ir`, `src/agentir/diagnostics`, and CLI modules. If strict mypy for all modules is too much in the first pass, document remaining issues in `TODO.md`.
10. README has a working quickstart.

## Do not stop early

Work through the phases in order. When you hit an implementation ambiguity, choose the simplest option that satisfies the spec and add a short note in `TODO.md`. Do not redesign the IR.

