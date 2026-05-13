# CLI Delta for AgentIR DSL

This document extends `docs/CLI.md` with DSL-aware commands.

## Existing commands must support DSL frontends

### `agentir-as`

Add:

```text
--frontend-dsl PATH              path to *.agentir.yaml
--dsl-name TEXT                  optional frontend name override
--allow-plugin-transform TEXT    explicit trusted plugin transform; repeatable
--raw-policy TEXT                full|external_ref|hash_only; defaults to spec
```

Examples:

```bash
agentir-as \
  --frontend-dsl dsl/formats/hermes_agent.agentir.yaml \
  --input samples/hermes.jsonl \
  --output out/hermes.dsl.raw.air.jsonl
```

`--frontend` and `--frontend-dsl` are mutually exclusive.

### `agentir compile`

Add:

```text
--frontend-dsl PATH
--passes spec:default|spec:recommended_for_training|TEXT
--dsl-report PATH
```

Example:

```bash
agentir compile \
  --frontend-dsl dsl/formats/openhands.agentir.yaml \
  --input samples/openhands.jsonl \
  --passes spec:default \
  --target process-supervision \
  --output out/openhands.ps.jsonl \
  --workdir out/openhands_compile
```

## New `agentir dsl` command group

```text
agentir dsl validate    validate DSL syntax and semantics
agentir dsl format      canonicalize DSL YAML formatting
agentir dsl init        create starter DSL from a template
agentir dsl probe       run detection and field coverage over sample rows
agentir dsl preview     show emitted AgentIR events for sample rows
agentir dsl compile     compile DSL to a runtime plan or generated Python frontend
agentir dsl bench       benchmark conversion speed
agentir dsl schema      export JSON Schema for the DSL itself
agentir dsl diff        compare two DSL specs or DSL vs Python frontend output
```

## `agentir dsl validate`

```bash
agentir dsl validate dsl/formats/hermes_agent.agentir.yaml
```

Options:

```text
SPEC                            required
--strict                        fail on warnings that indicate likely bad output
--schema-report PATH             write JSON validation report
--check-builtins                 verify all transforms/selectors are known
```

Exit codes:

- `0`: valid
- `1`: validation diagnostics contain errors
- `2`: CLI usage error

## `agentir dsl init`

```bash
agentir dsl init my-format --template native-tool-jsonl --output formats/my_format.agentir.yaml
```

Options:

```text
NAME                            required
--template TEXT                  minimal-sharegpt|native-tool-jsonl|hermes-xml|coding-agent
--output PATH                    required
--force                          overwrite existing file
```

## `agentir dsl probe`

Purpose: help users understand whether a spec matches sample data.

```bash
agentir dsl probe dsl/formats/openhands.agentir.yaml --input samples/openhands.jsonl --limit 20
```

Output should include Rich tables:

- detection score distribution;
- detection rule contributions;
- missing expected fields;
- selected paths and sample values;
- estimated event count;
- diagnostic summary.

Options:

```text
SPEC                            required
--input PATH                    required
--limit INT                     default: 20
--format json|jsonl|parquet     inferred
--show-values                   print sampled selected values
--json-report PATH              optional machine-readable report
```

## `agentir dsl preview`

Purpose: render a small number of parsed records.

```bash
agentir dsl preview dsl/formats/hermes_agent.agentir.yaml --input samples/hermes.jsonl --limit 3 --show-events
```

Options:

```text
--show-events                   table of emitted events
--show-record-json              print AgentIR JSON for each sample
--show-provenance               include source maps
--run-passes TEXT               optionally run passes before rendering
--output PATH                   optional preview markdown
```

## `agentir dsl compile`

Two modes:

### Plan mode

```bash
agentir dsl compile dsl/formats/hermes_agent.agentir.yaml --emit-plan out/hermes.plan.json
```

### Python generation mode

```bash
agentir dsl compile dsl/formats/hermes_agent.agentir.yaml \
  --emit-python src/agentir/frontends/generated/hermes_agent_dsl.py
```

Options:

```text
SPEC                            required
--emit-plan PATH                 serialized compiled plan for debugging
--emit-python PATH               generated Python frontend
--with-tests DIR                 generate golden tests into directory
--sample-input PATH              sample data used for generated tests
```

## `agentir dsl bench`

```bash
agentir dsl bench dsl/formats/claude_code.agentir.yaml --input traces.jsonl --limit 100000
```

Output metrics:

- records/sec;
- MB/sec;
- average events/record;
- selector time;
- transform time;
- emission time;
- validation time;
- top slow selectors/transforms;
- memory high-water mark if available.

Options:

```text
--limit INT
--batch-size INT
--jobs INT
--profile PATH                  write cProfile or pyinstrument-compatible report
--compare-python-frontend TEXT  compare DSL to registered Python frontend
```

## `agentir dsl diff`

Compare outputs.

```bash
agentir dsl diff \
  --dsl dsl/formats/openhands.agentir.yaml \
  --frontend openhands \
  --input tests/fixtures/openhands_sample.jsonl
```

It should report semantic differences:

- event count difference;
- event type sequence difference;
- role/content mismatch;
- tool name/argument mismatch;
- artifact/outcome mismatch;
- diagnostics mismatch.

## `agentir tui`

Launch terminal UI.

```bash
agentir tui dsl/formats/my_format.agentir.yaml --input samples/my_trace.jsonl
```

This is described in `DSL_TERMINAL_UI.md`.
