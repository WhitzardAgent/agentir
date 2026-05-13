# AgentIR

**AgentIR** is a compiler infrastructure for agentic trajectories. It turns heterogeneous traces from agent frameworks, coding agents, GUI/browser agents, tool-use agents, evaluation sandboxes, and research datasets into a canonical intermediate representation that can be verified, transformed, analyzed, and lowered into training, evaluation, replay, observability, and framework-specific targets.

> Core thesis: **make agentic trajectories compilable.**

AgentIR should become the **LLVM for agent trajectories**:

```text
Source agent traces
  AgentTrove / Codex / Claude Code / OpenHands / Hermes / LangGraph / AutoGen / MCP logs / custom JSONL / custom Parquet
        ↓
Frontends
  handwritten Python frontends or user-defined *.agentir.yaml DSL frontends
        ↓
RawIR / ParsedIR / Canonical AgentIR
        ↓
Verifier + Analysis/Transformation Passes
        ↓
Backends / Lowering Targets
        ↓
SFT / Tool-use / Process Supervision / RL / DPO / OpenAI Tools / Anthropic Tools / Hermes XML / OpenHands / OTel/OpenInference
```

## What this document package is

This is a **full overwrite-ready documentation package** for the AgentIR repository. It is designed to be copied into the repository root.

It intentionally **does not include `src/` or `tests/`**, so it will not overwrite your existing implementation or tests. It replaces and expands repository-level docs, specs, examples, DSL definitions, schema notes, and Claude Code prompts.

See [`APPLY_OVERWRITE.md`](APPLY_OVERWRITE.md) for the recommended copy command.

## Non-negotiable design principles

1. **Compiler-style architecture, not a one-off converter.** AgentIR must keep explicit frontends, IR models, verifier, pass manager, diagnostics, source maps, and backends.
2. **Python-first for v0.1/v0.2.** The target ecosystem is Hugging Face Datasets, Parquet/Arrow, Pydantic schemas, Typer/Rich CLIs, and ML training pipelines.
3. **Lossless ingestion, canonical middle-end, loss-aware lowering.** Preserve raw source rows; normalize into canonical AgentIR; require backend loss reports.
4. **Event graph, not just messages.** Messages are one projection. The canonical unit is an event with action, observation, artifact, state, control, outcome, and provenance.
5. **Pass-based processing.** Parsing, canonicalization, pairing, redaction, slicing, verification, and lowering must remain separate passes.
6. **User-extensible format DSL.** Users should define new trajectory formats with `*.agentir.yaml` whenever possible instead of writing custom Python frontends.
7. **Terminal-first developer experience.** Users should be able to validate, probe, preview, diff, benchmark, and debug format specs from the terminal.
8. **Conversion efficiency matters.** Support streaming JSONL, batched processing, compiled selectors, Parquet/Arrow paths, bounded regex/XML parsing, and optional generated Python frontends.
9. **Compiler-style diagnostics.** Use diagnostic codes, source references, coverage reports, and suggested fixes.
10. **Global open-source quality.** Typed code, strong tests, clean CLI, stable spec, examples, docs, CI-ready layout.

## v0.1/v0.2 scope

The first milestone proves the compiler architecture with five real-world trace families and their DSL equivalents:

| Format | Dataset / source | Required support | DSL spec |
|---|---|---|---|
| `agenttrove` | `open-thoughts/AgentTrove` | ShareGPT-like messages, reward, source metadata, weakly structured tool text | `dsl/formats/agenttrove.agentir.yaml` |
| `codex-swebenchpro` | `Inferact/codex_swebenchpro_traces` | ShareGPT-like coding traces, long text logs, optional SWE outcome metadata | `dsl/formats/codex_swebenchpro.agentir.yaml` |
| `claude-code` | `nlile/misc-merged-claude-code-traces-v1` | `messages_json`, `tools_json`, `gitdiff`, `claude_log`, incomplete rows | `dsl/formats/claude_code.agentir.yaml` |
| `openhands` | `nvidia/SWE-Hero-openhands-trajectories` | structured `trajectory`, `tool_calls`, repo metadata, `model_patch` | `dsl/formats/openhands.agentir.yaml` |
| `hermes-agent` | `lambda/hermes-agent-reasoning-traces` | ShareGPT + `<think>`, `<tool_call>`, `<tool_response>`, tool schemas | `dsl/formats/hermes_agent.agentir.yaml` |

The key architectural change is that these five formats should continue to work through handwritten frontends, but they should also be expressible as declarative DSL specs. The DSL output must be semantically equivalent to the handwritten frontend output on fixtures.

## Required first commands

Core compiler-style pipeline:

```bash
agentir-as --frontend hermes-agent --input samples/hermes.jsonl --output out/hermes.raw.air.jsonl
agentir-opt out/hermes.raw.air.jsonl --passes parse-hermes-xml,canonicalize-tools,pair-tool-results,normalize-outcome,verify --output out/hermes.canonical.air.jsonl
agentir-llc out/hermes.canonical.air.jsonl --target sft --output out/hermes.sft.jsonl --loss-report out/hermes.loss.md
agentir verify out/hermes.canonical.air.jsonl --strict --report out/hermes.verify.md
```

DSL-defined frontend pipeline:

```bash
agentir dsl validate dsl/formats/hermes_agent.agentir.yaml
agentir dsl probe dsl/formats/hermes_agent.agentir.yaml --input samples/hermes.jsonl --limit 3
agentir dsl preview dsl/formats/hermes_agent.agentir.yaml --input samples/hermes.jsonl --limit 3 --show-events
agentir-as --frontend-dsl dsl/formats/hermes_agent.agentir.yaml --input samples/hermes.jsonl --output out/hermes.dsl.raw.air.jsonl
agentir compile --frontend-dsl dsl/formats/hermes_agent.agentir.yaml --input samples/hermes.jsonl --target sft --output out/hermes.dsl.sft.jsonl --loss-report out/hermes.dsl.loss.md
```

Terminal UX and performance workflow:

```bash
agentir dsl init --template native-tool-jsonl --output dsl/formats/my_agent.agentir.yaml
agentir dsl preview dsl/formats/my_agent.agentir.yaml --input data/my_agent.jsonl --limit 5 --show-events --show-diagnostics
agentir dsl bench dsl/formats/my_agent.agentir.yaml --input data/my_agent.jsonl --limit 10000
agentir dsl diff dsl/formats/my_agent.agentir.yaml --against dsl/formats/hermes_agent.agentir.yaml --input samples/hermes.jsonl
```

## Repository documents

Core compiler docs:

- `docs/DESIGN.md` — architecture and compiler model.
- `docs/SPEC.md` — AgentIR v0.1 schema.
- `docs/DIALECTS.md` — core/tool/terminal/file/browser/SWE/reasoning/eval dialects.
- `docs/PASSES.md` — pass registry and required pass behavior.
- `docs/FRONTENDS.md` — handwritten parsing rules for the five initial datasets.
- `docs/BACKENDS.md` — lowering targets and loss-report behavior.
- `docs/CLI.md` — CLI specification.
- `docs/DIAGNOSTICS.md` — diagnostic model and codes.
- `docs/TESTING.md` — test strategy and acceptance criteria.
- `docs/ROADMAP.md` — staged development plan.
- `docs/PROJECT_STRUCTURE.md` — required repository layout.
- `docs/STACK.md` — technology stack and rationale.

DSL docs:

- `docs/DSL.md` — integrated DSL index.
- `README_DSL_EXTENSION.md` — DSL extension summary.
- `docs/dsl/DSL_OVERVIEW.md` — architecture and mental model.
- `docs/dsl/DSL_SPEC.md` — YAML DSL schema and semantics.
- `docs/dsl/DSL_RUNTIME.md` — runtime frontend compilation.
- `docs/dsl/DSL_BUILTINS.md` — selectors, transforms, emitters, parser primitives.
- `docs/dsl/DSL_AUTHORING_GUIDE.md` — how users add a new trajectory format.
- `docs/dsl/DSL_TERMINAL_UI.md` — terminal UI requirements.
- `docs/dsl/DSL_PERFORMANCE.md` — streaming, batching, selector compilation, caching, benchmark requirements.
- `docs/dsl/DSL_TESTING.md` — golden tests, equivalence tests, acceptance criteria.
- `docs/dsl/DSL_SECURITY.md` — no unsafe eval, regex/XML limits, plugin trust model.
- `docs/dsl/DSL_PROJECT_STRUCTURE_DELTA.md` — implementation delta from the original project structure.
- `docs/dsl/DSL_CLI_DELTA.md` — new CLI commands and flags.
- `docs/dsl/DSL_DIAGNOSTICS_DELTA.md` — diagnostic code additions.
- `docs/dsl/DSL_ROADMAP.md` — phased implementation plan.

DSL specs and examples:

- `dsl/formats/*.agentir.yaml` — built-in DSL specs for the five representative formats.
- `dsl/templates/*.agentir.yaml` — reusable authoring templates.
- `examples/user_defined/react_agent_jsonl.agentir.yaml` — custom ReAct JSONL example.

Claude Code prompts:

- `prompts/CLAUDE_CODE_MASTER_PROMPT.md` — original implementation prompt.
- `prompts/CLAUDE_CODE_DSL_EXTENSION_PROMPT.md` — DSL implementation prompt.
- `prompts/CLAUDE_CODE_FULL_OVERWRITE_PROMPT.md` — recommended full-repo implementation prompt after applying this document package.

## Recommended implementation order

1. Align the repository docs with this package.
2. Preserve existing `src/` and `tests/` implementation.
3. Implement DSL schema models and validation.
4. Implement safe selector, expression, condition, transform, and emitter engines.
5. Implement `RuntimeDSLFrontend` and `agentir-as --frontend-dsl`.
6. Add CLI commands: `validate`, `probe`, `preview`, `compile`, `bench`, `diff`, `init`, `schema export`.
7. Encode the five existing frontends as DSL specs and add equivalence tests.
8. Add Rich terminal preview/probe/bench UX.
9. Optimize throughput with streaming, compiled selectors, batching, Arrow/Parquet paths, and optional generated Python frontends.

## Acceptance bar

The work is complete only when:

1. Existing handwritten frontends still work.
2. Existing tests still pass.
3. All built-in `dsl/formats/*.agentir.yaml` specs validate.
4. All built-in DSL specs parse fixtures.
5. DSL output is semantically equivalent to handwritten frontend output on fixtures.
6. `agentir-as --frontend-dsl` works.
7. `agentir compile --frontend-dsl --passes spec:default` works.
8. `agentir dsl probe`, `preview`, `bench`, and `diff` produce useful terminal output.
9. DSL evaluation uses no unsafe `eval`/`exec` and no untrusted plugin execution by default.
