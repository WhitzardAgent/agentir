# DSL Roadmap

## Phase DSL-0: Documentation and examples

Deliverables:

- DSL overview, spec, runtime, CLI, TUI, performance, testing, and security docs.
- YAML DSL examples for the five existing representative formats.
- User-defined templates.
- Claude Code implementation prompt.

Acceptance:

- docs are self-contained;
- examples are consistent with the existing AgentIR v0.1 schema;
- implementation work can start without redesigning the architecture.

## Phase DSL-1: Schema and validation

Implement:

- Pydantic DSL models;
- YAML loader with `ruamel.yaml`;
- `agentir dsl validate`;
- DSL JSON Schema export;
- semantic validation for selectors/transforms/event rules.

Acceptance:

```bash
agentir dsl validate dsl/formats/*.agentir.yaml
agentir dsl schema export --output schema/agentir.format_dsl.schema.v0.1.json
```

## Phase DSL-2: Selector and expression engine

Implement:

- restricted JSONPath-like selectors;
- `first_of`, `const`, `template`, `default`, `transform` expressions;
- condition evaluator;
- missing value model;
- selector diagnostics.

Acceptance:

- selector unit tests pass;
- selectors are compiled once per spec;
- missing optional fields do not crash runtime.

## Phase DSL-3: Runtime DSL frontend

Implement:

- `DSLCompiler`;
- `RuntimeDSLFrontend`;
- actor/task/tool/artifact/event/outcome emitters;
- provenance generation;
- raw row preservation;
- `agentir-as --frontend-dsl`.

Acceptance:

- minimal ShareGPT template parses fixture;
- native tool JSONL template parses fixture;
- output is valid `AgentIRRecord` JSONL.

## Phase DSL-4: Built-in format parity

Encode these existing formats as DSL:

- AgentTrove
- Codex SWE-bench Pro
- Claude Code
- OpenHands
- Hermes Agent

Acceptance:

- all five DSL specs validate;
- all five parse fixtures;
- semantic equivalence tests pass against hand-written Python frontends.

## Phase DSL-5: CLI and terminal authoring UX

Implement:

- `agentir dsl probe`;
- `agentir dsl preview`;
- `agentir dsl init`;
- `agentir dsl format`;
- `agentir dsl diff`;
- optional `agentir tui` full-screen app.

Acceptance:

- a user can author a new format from samples without editing Python;
- probe/preview output is useful over SSH;
- TUI is optional and not required for CI.

## Phase DSL-6: Performance path

Implement:

- `agentir dsl bench`;
- per-stage timing;
- compiled selector cache;
- bounded diagnostics aggregation;
- multiprocessing for JSONL shards if straightforward;
- optional generated Python frontend.

Acceptance:

- streaming conversion is memory stable;
- benchmark reports bottlenecks;
- generated frontend output matches runtime mode on fixtures.

## Phase DSL-7: Ecosystem expansion

Add community specs for:

- LangGraph traces;
- AutoGen traces;
- CrewAI traces;
- LlamaIndex agent traces;
- MCP logs;
- OpenAI Agents SDK traces;
- browser/computer-use agent traces;
- cybersecurity agent sandbox trajectories.

Acceptance:

- each spec includes sample fixture, golden snapshot, and loss-report example;
- specs can be contributed without modifying core AgentIR code.
