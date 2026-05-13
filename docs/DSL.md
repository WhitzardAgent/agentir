# AgentIR Format DSL

AgentIR has two frontend paths:

1. **Handwritten Python frontends** for complex or high-value formats.
2. **Declarative `*.agentir.yaml` DSL frontends** for user-defined trajectory formats.

The DSL path is the major extension that turns AgentIR from a fixed converter into a reusable compiler infrastructure for agent trajectory data.

## Goal

Users should be able to define a new trace format by writing a YAML spec:

```yaml
apiVersion: agentir.qitor.ai/v0.1
kind: TrajectoryFormat
metadata:
  name: my-react-agent
source:
  kind: jsonl
detect:
  rules:
    - field_exists: $.messages
mapping:
  events:
    - foreach: $.messages[*]
      emit: message_event
      fields:
        type:
          transform: role_to_event_type
          input: $.role
        text: $.content
```

Then convert it through the normal AgentIR compiler pipeline:

```bash
agentir dsl validate dsl/formats/my_react_agent.agentir.yaml
agentir dsl preview dsl/formats/my_react_agent.agentir.yaml --input data/traces.jsonl --limit 5 --show-events
agentir-as --frontend-dsl dsl/formats/my_react_agent.agentir.yaml --input data/traces.jsonl --output out/raw.air.jsonl
agentir compile --frontend-dsl dsl/formats/my_react_agent.agentir.yaml --input data/traces.jsonl --target sft --output out/sft.jsonl
```

## Mental model

```text
source row
  ↓ detection rules
selected/bound fields
  ↓ transforms + emitters
Raw/Parsed AgentIR
  ↓ normal pass manager
Canonical AgentIR
  ↓ loss-aware backend lowering
training / evaluation / replay / observability target
```

The DSL must never bypass AgentIR IR, passes, diagnostics, or backends.

## Design constraints

- No arbitrary Python `eval` or `exec`.
- Bounded regex and XML parsing.
- Plugins disabled by default.
- Raw rows preserved by default.
- Source maps and provenance attached whenever possible.
- Rich diagnostics for selector errors, missing fields, transform failures, and lossy mappings.
- Streaming-first conversion for JSONL and batched paths for large datasets.

## Main documents

- `docs/dsl/DSL_OVERVIEW.md` — high-level architecture.
- `docs/dsl/DSL_SPEC.md` — YAML schema and field semantics.
- `docs/dsl/DSL_BUILTINS.md` — built-in selectors, expressions, transforms, emitters.
- `docs/dsl/DSL_RUNTIME.md` — runtime frontend compilation and execution.
- `docs/dsl/DSL_AUTHORING_GUIDE.md` — author workflow.
- `docs/dsl/DSL_TERMINAL_UI.md` — Rich/Textual UX.
- `docs/dsl/DSL_PERFORMANCE.md` — streaming and optimization requirements.
- `docs/dsl/DSL_TESTING.md` — fixture, golden, and equivalence tests.
- `docs/dsl/DSL_SECURITY.md` — safety constraints.
- `docs/dsl/DSL_CLI_DELTA.md` — CLI additions.
- `docs/dsl/DSL_ROADMAP.md` — staged implementation.

## Built-in DSL specs

The five initial representative formats must exist both as Python frontends and DSL specs:

```text
dsl/formats/agenttrove.agentir.yaml
dsl/formats/codex_swebenchpro.agentir.yaml
dsl/formats/claude_code.agentir.yaml
dsl/formats/openhands.agentir.yaml
dsl/formats/hermes_agent.agentir.yaml
```

Each built-in DSL spec must have equivalence tests against the corresponding handwritten frontend.

## Terminal UX expectation

The DSL workflow should be terminal-native:

```bash
agentir dsl validate dsl/formats/hermes_agent.agentir.yaml
agentir dsl probe dsl/formats/hermes_agent.agentir.yaml --input samples/hermes.jsonl --limit 5
agentir dsl preview dsl/formats/hermes_agent.agentir.yaml --input samples/hermes.jsonl --show-events --show-diagnostics
agentir dsl bench dsl/formats/hermes_agent.agentir.yaml --input samples/hermes.jsonl --limit 10000
agentir dsl diff dsl/formats/hermes_agent.agentir.yaml --against handwritten:hermes-agent --input samples/hermes.jsonl
```

The first version can be Rich-based and non-fullscreen. A Textual fullscreen TUI is optional and should degrade gracefully when Textual is unavailable.
