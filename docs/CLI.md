# CLI Specification

agentir must expose both compiler-style commands and a friendly umbrella command.

## Commands

```text
agentir-as       frontend parser: source → RawIR/ParsedIR
agentir-opt      pass pipeline: IR → IR
agentir-llc      lowering backend: IR → target format
agentir          umbrella command with subcommands
```

## `agentir-as`

Purpose: parse source dataset/local file into `.air.jsonl` or `.air.parquet`.

Examples:

```bash
agentir-as \
  --frontend hermes-agent \
  --hf-dataset lambda/hermes-agent-reasoning-traces \
  --config glm-5.1 \
  --split train \
  --limit 1000 \
  --output out/hermes.raw.air.jsonl

agentir-as \
  --frontend openhands \
  --input samples/openhands.jsonl \
  --output out/openhands.raw.air.jsonl
```

Options:

```text
--frontend TEXT                 required
--input PATH                    local input path
--hf-dataset TEXT               Hugging Face dataset ID
--config TEXT                   HF config
--split TEXT                    default: train
--streaming / --no-streaming    default: true for HF
--limit INT                     optional
--output PATH                   required
--format jsonl|parquet          inferred from output if omitted
--strict                        fail on parse errors
--debug                         include verbose diagnostics
```

## `agentir-opt`

Purpose: run pass pipeline.

Example:

```bash
agentir-opt out/hermes.raw.air.jsonl \
  --passes parse-hermes-xml,canonicalize-tools,pair-tool-results,extract-patches,normalize-outcome,verify \
  --output out/hermes.canonical.air.jsonl
```

Options:

```text
INPUT                           required
--passes TEXT                   comma-separated pass names
--output PATH                   required
--reasoning-policy TEXT         preserve|summarize|drop|redact|metadata_only
--strict                        strict verifier behavior
--report PATH                   optional markdown report
--format jsonl|parquet          inferred
```

## `agentir-llc`

Purpose: lower AgentIR into target format.

Example:

```bash
agentir-llc out/hermes.canonical.air.jsonl \
  --target sft \
  --output out/hermes.sft.jsonl \
  --loss-report out/hermes.loss.md
```

Options:

```text
INPUT                           required
--target TEXT                   required: sft|process-supervision|openai-tools|hermes-xml|openhands|sharegpt
--output PATH                   required
--loss-report PATH              optional but recommended
--reasoning-policy TEXT         default: metadata_only
--include-reasoning             explicit override
--tool-policy TEXT              structured|inline|drop
--format jsonl|parquet          inferred
```

## `agentir verify`

Purpose: run verifier only.

```bash
agentir verify out/hermes.canonical.air.jsonl --strict --report out/verify.md
```

## `agentir schema export`

Purpose: export JSON Schema from Pydantic models.

```bash
agentir schema export --output schema/agentir.schema.v0.1.json
```

## `agentir compile`

Friendly one-shot command.

```bash
agentir compile \
  --frontend hermes-agent \
  --hf-dataset lambda/hermes-agent-reasoning-traces \
  --split train \
  --limit 1000 \
  --passes parse-hermes-xml,canonicalize-tools,pair-tool-results,normalize-outcome,verify \
  --target sft \
  --output out/hermes.sft.jsonl \
  --workdir out/hermes_compile
```

This must internally run:

1. `agentir-as`
2. `agentir-opt`
3. `agentir-llc`

and keep intermediate artifacts unless `--clean` is passed.

## UX requirements

- Use Rich tables for summaries.
- Print progress every N records for large jobs.
- Never hide diagnostics.
- Exit codes:
  - `0`: success
  - `1`: diagnostics include errors
  - `2`: CLI usage error
  - `3`: unsupported frontend/backend/pass
  - `4`: verifier failed in strict mode


## DSL frontend options

`agentir-as` must also support DSL-defined frontends:

```bash
agentir-as \
  --frontend-dsl dsl/formats/hermes_agent.agentir.yaml \
  --input samples/hermes.jsonl \
  --output out/hermes.dsl.raw.air.jsonl
```

Additional options:

```text
--frontend-dsl PATH             path to *.agentir.yaml format spec
--dsl-strict                    fail on DSL diagnostics with severity error
--dsl-plugin-policy TEXT        disabled|allow-listed|all; default disabled
--emit-plan PATH                write compiled DSL execution plan for debugging
```

`--frontend` and `--frontend-dsl` are mutually exclusive. Handwritten frontends remain the default for built-in names; DSL frontends are explicit unless the registry later provides aliases.

## `agentir dsl`

Purpose: validate, debug, compile, and benchmark user-defined trajectory format specs.

### `agentir dsl validate`

```bash
agentir dsl validate dsl/formats/hermes_agent.agentir.yaml
```

Validates YAML syntax, top-level schema, selector syntax, known transforms, known emitters, and basic mapping structure.

### `agentir dsl schema export`

```bash
agentir dsl schema export --output schema/agentir.format_dsl.schema.v0.1.json
```

Exports JSON Schema for the DSL Pydantic models.

### `agentir dsl init`

```bash
agentir dsl init --template minimal-sharegpt --output dsl/formats/my_format.agentir.yaml
agentir dsl init --template native-tool-jsonl --output dsl/formats/my_tools.agentir.yaml
```

Creates a starter spec from a built-in template.

### `agentir dsl probe`

```bash
agentir dsl probe dsl/formats/hermes_agent.agentir.yaml --input samples/hermes.jsonl --limit 5
```

Shows detection-rule matches, field coverage, selector failures, and high-level row classification.

### `agentir dsl preview`

```bash
agentir dsl preview dsl/formats/hermes_agent.agentir.yaml \
  --input samples/hermes.jsonl \
  --limit 5 \
  --show-events \
  --show-diagnostics
```

Shows emitted AgentIR records/events without writing the full output.

### `agentir dsl compile`

```bash
agentir dsl compile dsl/formats/hermes_agent.agentir.yaml \
  --input samples/hermes.jsonl \
  --output out/hermes.raw.air.jsonl \
  --emit-plan out/hermes.dsl.plan.json
```

Compiles a source file into Raw/Parsed AgentIR using the DSL frontend.

### `agentir dsl bench`

```bash
agentir dsl bench dsl/formats/openhands.agentir.yaml --input samples/openhands.jsonl --limit 10000
```

Reports rows/s, events/s, diagnostic rate, peak memory when available, and time breakdown by detect/select/transform/emit/write.

### `agentir dsl diff`

```bash
agentir dsl diff dsl/formats/hermes_agent.agentir.yaml \
  --against handwritten:hermes-agent \
  --input samples/hermes.jsonl \
  --limit 100
```

Compares DSL output against a handwritten frontend or another DSL spec. This is required for equivalence testing of built-in formats.

## `agentir tui`

Optional fullscreen TUI for interactive DSL authoring and debugging:

```bash
agentir tui dsl/formats/openhands.agentir.yaml --input samples/openhands.jsonl
```

If Textual is unavailable, this must degrade gracefully and print the equivalent non-fullscreen commands:

```bash
agentir dsl probe ...
agentir dsl preview ...
agentir dsl bench ...
```
