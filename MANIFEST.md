# AgentIR Full Documentation Overlay Manifest

This package is a complete overwrite-ready documentation package for an existing `agentir` repository.

It intentionally does **not** include `src/` or `tests/`, so it can be applied to a repository where implementation code and tests already exist.

## Top-level files

- `README.md` — integrated AgentIR + DSL overview.
- `README_DSL_EXTENSION.md` — DSL extension summary.
- `APPLY_OVERWRITE.md` — safe copy/rsync instructions.
- `MANIFEST.md` — this file.
- `pyproject.template.toml` — dependency/configuration reference.

## Core compiler documents

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
- `docs/STACK.md`
- `docs/IMPLEMENTATION_NOTES.md`

## DSL documents

- `docs/DSL.md`
- `docs/dsl/DSL_OVERVIEW.md`
- `docs/dsl/DSL_SPEC.md`
- `docs/dsl/DSL_BUILTINS.md`
- `docs/dsl/DSL_RUNTIME.md`
- `docs/dsl/DSL_AUTHORING_GUIDE.md`
- `docs/dsl/DSL_CLI_DELTA.md`
- `docs/dsl/DSL_TERMINAL_UI.md`
- `docs/dsl/DSL_PERFORMANCE.md`
- `docs/dsl/DSL_TESTING.md`
- `docs/dsl/DSL_SECURITY.md`
- `docs/dsl/DSL_DIAGNOSTICS_DELTA.md`
- `docs/dsl/DSL_PROJECT_STRUCTURE_DELTA.md`
- `docs/dsl/DSL_ROADMAP.md`

## Built-in DSL specifications

- `dsl/formats/agenttrove.agentir.yaml`
- `dsl/formats/codex_swebenchpro.agentir.yaml`
- `dsl/formats/claude_code.agentir.yaml`
- `dsl/formats/openhands.agentir.yaml`
- `dsl/formats/hermes_agent.agentir.yaml`

## Templates and examples

- `dsl/templates/minimal_sharegpt.agentir.yaml`
- `dsl/templates/native_tool_jsonl.agentir.yaml`
- `examples/user_defined/react_agent_jsonl.agentir.yaml`

## Schema notes

- `schema/agentir.schema.v0.1.note.md`
- `schema/format_dsl.schema.v0.1.note.md`

## Claude Code prompts

- `prompts/CLAUDE_CODE_MASTER_PROMPT.md`
- `prompts/CLAUDE_CODE_DSL_EXTENSION_PROMPT.md`
- `prompts/CLAUDE_CODE_FULL_OVERWRITE_PROMPT.md`

## Apply command

```bash
rsync -av --delete \
  --exclude 'src/' \
  --exclude 'tests/' \
  agentir_full_docs_overwrite/ /path/to/agentir/
```

## Implementation target after applying

The repository should support both:

```bash
agentir-as --frontend hermes-agent --input samples/hermes.jsonl --output out/hermes.raw.air.jsonl
```

and:

```bash
agentir-as --frontend-dsl dsl/formats/hermes_agent.agentir.yaml --input samples/hermes.jsonl --output out/hermes.dsl.raw.air.jsonl
```
