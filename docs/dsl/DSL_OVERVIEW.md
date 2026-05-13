# AgentIR Format DSL Overview

## Mission

The AgentIR Format DSL lets users define new agent trajectory source formats without writing a full Python frontend.

A format DSL file is a declarative specification that tells `agentir` how to:

1. detect whether a source record belongs to this format;
2. bind source fields into named values;
3. parse nested JSON/XML/tool blocks when needed;
4. emit AgentIR actors, tools, task metadata, artifacts, episodes, and events;
5. attach source maps/provenance;
6. run the normal AgentIR pass pipeline;
7. verify and lower the result into target formats.

The DSL is not a replacement for AgentIR. It is a user-facing frontend-definition layer.

```text
JSONL / JSON / Parquet / HF row
        ↓
Trajectory Format DSL
        ↓
RuntimeDSLFrontend or generated Python frontend
        ↓
RawIR / ParsedIR
        ↓
Pass manager
        ↓
Canonical AgentIR
        ↓
Backends
```

## Why this is necessary

Agent trajectory data is highly fragmented:

- ShareGPT-like traces use `from/value`, `role/content`, or framework-specific aliases.
- Tool calls may appear as native structured arrays, JSON embedded in text, XML blocks, shell transcripts, or Markdown code blocks.
- Coding agents mix messages, terminal commands, file patches, logs, browser actions, verifier outputs, and final answers.
- Some datasets only contain final conversations; others contain full event streams with tool IDs and observations.

Hand-writing a Python frontend for every new format does not scale. The DSL turns common parsing patterns into reusable declarations.

## LLVM analogy

AgentIR should act like LLVM for agent trajectories.

| LLVM/MLIR concept | AgentIR equivalent |
|---|---|
| Language frontend | DSL-defined trajectory format frontend |
| TableGen/declarative op definitions | `*.agentir.yaml` format specs |
| Debug metadata | provenance/source maps |
| IR verifier | AgentIR verifier |
| Middle-end passes | parser/canonicalizer/analysis/transformation passes |
| Backend lowering | training/eval/replay/framework exports |
| Optimization reports | loss reports, quality reports, diagnostic summaries |

The important point: a user-defined DSL frontend must still produce typed AgentIR events and must still pass the verifier.

## DSL file types

Use the suffix:

```text
*.agentir.yaml
```

Recommended locations:

```text
agentir/
  dsl/
    formats/          # built-in format DSLs
    templates/        # reusable starter specs
  user_formats/       # local user-defined specs, ignored by git by default
```

## Runtime vs generated frontend

The same DSL spec can run in two modes.

### Runtime mode

```bash
agentir-as --frontend-dsl formats/my_format.agentir.yaml --input traces.jsonl --output out.air.jsonl
```

Pros:

- fastest to iterate;
- no generated code;
- good for user-defined formats and one-off conversions.

Cons:

- slower than a hand-optimized Python frontend for very large corpora;
- selector and transform dispatch overhead exists.

### Generated mode

```bash
agentir dsl compile formats/my_format.agentir.yaml \
  --emit-python src/agentir/frontends/generated/my_format.py
```

Pros:

- faster on large corpora;
- easier to profile;
- can be registered like a normal frontend.

Cons:

- generated code must be reviewed;
- less convenient during format authoring.

## DSL scope

The DSL should cover 80–90% of practical trajectory ingestion needs:

- mapping source fields to AgentIR fields;
- iterating over message arrays and event arrays;
- parsing native tool calls;
- parsing JSON strings;
- parsing XML-like tool blocks;
- extracting patches, terminal transcripts, and tool results;
- applying role aliases;
- emitting warnings for missing/empty fields;
- configuring default pass pipelines.

The DSL should not attempt to solve everything. Complex or highly custom formats can still use Python frontends or trusted plugin transforms.

## Non-goals

1. Do not embed arbitrary Python expressions in YAML.
2. Do not silently drop source fields.
3. Do not bypass AgentIR verifier or pass pipeline.
4. Do not make target-specific training outputs directly from source rows.
5. Do not let the DSL mutate the canonical AgentIR schema.
6. Do not use LLM calls during parsing.

## User workflow

```bash
# 1. Create starter spec
agentir dsl init my-agent-format --template native-tool-jsonl --output formats/my_agent.agentir.yaml

# 2. Validate the DSL itself
agentir dsl validate formats/my_agent.agentir.yaml

# 3. Probe sample records and inspect field coverage
agentir dsl probe formats/my_agent.agentir.yaml --input samples/my_agent.jsonl --limit 20

# 4. Preview emitted AgentIR events for a few rows
agentir dsl preview formats/my_agent.agentir.yaml --input samples/my_agent.jsonl --limit 3

# 5. Convert to AgentIR
agentir-as --frontend-dsl formats/my_agent.agentir.yaml --input samples/my_agent.jsonl --output out/my_agent.raw.air.jsonl

# 6. Run normal passes
agentir-opt out/my_agent.raw.air.jsonl --passes canonicalize-tools,pair-tool-results,extract-patches,normalize-outcome,verify --output out/my_agent.canonical.air.jsonl

# 7. Lower into training format
agentir-llc out/my_agent.canonical.air.jsonl --target process-supervision --output out/my_agent.ps.jsonl --loss-report out/my_agent.loss.md
```

## Design invariant

Every DSL-defined frontend must satisfy these invariants:

- source row is preserved under `raw.record` unless `raw_policy` explicitly uses external raw references;
- every emitted parsed event has provenance when possible;
- every inferred field has confidence below `1.0` unless the source explicitly provides it;
- every lossy or uncertain operation emits diagnostics;
- downstream passes and backends see normal AgentIR records, not special DSL objects.
