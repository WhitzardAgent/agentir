# AgentIR DSL Extension Pack

This extension pack upgrades `agentir` from a fixed set of hand-written frontends into a compiler infrastructure where users can define new agent trajectory formats through a declarative DSL.

The goal is explicit:

> **AgentIR should become the LLVM for agent trajectories.**

In that analogy:

| Compiler layer | AgentIR layer |
|---|---|
| Source language grammar | User-defined trajectory format DSL |
| Lexer/parser/frontend | DSL runtime frontend or generated Python frontend |
| Debug info | provenance/source maps |
| LLVM/MLIR IR | canonical AgentIR |
| Optimization passes | trajectory parse/canonicalize/analysis passes |
| Backend target | SFT, RL rollout, process supervision, OpenAI tools, Hermes XML, OpenHands, OTel, etc. |
| `clang`/`llc`/`opt` UX | `agentir-as`, `agentir-opt`, `agentir-llc`, `agentir compile`, `agentir tui` |

## What this pack adds

New documentation:

- `docs/dsl/DSL_OVERVIEW.md` — architecture and mental model.
- `docs/dsl/DSL_SPEC.md` — exact YAML DSL schema and semantics.
- `docs/dsl/DSL_RUNTIME.md` — how DSL specs compile into runtime frontends.
- `docs/dsl/DSL_BUILTINS.md` — selectors, transforms, emitters, and parser primitives.
- `docs/dsl/DSL_AUTHORING_GUIDE.md` — how users add a new trajectory format.
- `docs/dsl/DSL_TERMINAL_UI.md` — terminal UI and interactive format authoring requirements.
- `docs/dsl/DSL_PERFORMANCE.md` — streaming, batching, selector compilation, caching, and benchmarking.
- `docs/dsl/DSL_TESTING.md` — golden tests, equivalence tests, and acceptance criteria.
- `docs/dsl/DSL_SECURITY.md` — no unsafe eval, regex/XML limits, plugin trust model.
- `docs/dsl/DSL_PROJECT_STRUCTURE_DELTA.md` — implementation delta to the existing repository structure.
- `docs/dsl/DSL_CLI_DELTA.md` — new CLI commands and options.
- `docs/dsl/DSL_DIAGNOSTICS_DELTA.md` — diagnostic code additions.
- `docs/dsl/DSL_ROADMAP.md` — phased implementation plan.

DSL examples for the five initial representative formats:

- `dsl/formats/agenttrove.agentir.yaml`
- `dsl/formats/codex_swebenchpro.agentir.yaml`
- `dsl/formats/claude_code.agentir.yaml`
- `dsl/formats/openhands.agentir.yaml`
- `dsl/formats/hermes_agent.agentir.yaml`

Reusable templates:

- `dsl/templates/minimal_sharegpt.agentir.yaml`
- `dsl/templates/native_tool_jsonl.agentir.yaml`
- `examples/user_defined/react_agent_jsonl.agentir.yaml`

Claude Code execution prompt:

- `prompts/CLAUDE_CODE_DSL_EXTENSION_PROMPT.md`

## Design principle

The DSL must reduce the cost of adding a new frontend without weakening the compiler architecture.

It must not become a loose JSON converter. A DSL-defined format still goes through:

```text
source row
  ↓ DSL detection + binding + event emission
Raw/Parsed AgentIR
  ↓ normal AgentIR pass pipeline
Canonical AgentIR
  ↓ loss-aware lowering
training/eval/replay/framework target
```

## Recommended implementation order

1. Implement DSL schema models and validation.
2. Implement safe selector engine.
3. Implement built-in transforms and emitters.
4. Implement `RuntimeDSLFrontend`.
5. Add CLI commands: `agentir dsl validate`, `probe`, `preview`, `compile`, `bench`, `init`.
6. Encode the five existing hand-written frontends as DSL specs.
7. Add equivalence tests: Python frontend output vs DSL frontend output on fixtures.
8. Build terminal UI for interactive authoring/debugging.
9. Optimize conversion throughput with streaming, compiled selectors, Arrow/Parquet batch paths, and optional generated Python frontend.

