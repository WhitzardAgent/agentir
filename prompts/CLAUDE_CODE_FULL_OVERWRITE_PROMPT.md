# Claude Code Prompt: Implement AgentIR as a Trajectory Compiler with DSL Frontends

You are Claude Code working in the existing `agentir` repository.

The repository may already contain useful implementation code under `src/` and tests under `tests/`. Preserve that work. Do not delete or rewrite it wholesale. Your job is to align the implementation with the documentation package now present at the repository root and extend the repo with the AgentIR format DSL.

## Product goal

AgentIR is the LLVM for agent trajectories.

It should support:

```text
source trace format
  ↓ handwritten Python frontend OR user-defined *.agentir.yaml DSL frontend
Raw/Parsed AgentIR
  ↓ verifier + analysis/transformation passes
Canonical AgentIR
  ↓ loss-aware backend lowering
SFT / tool-use / process supervision / RL / eval / replay / observability targets
```

## Read first

Read these core docs:

- `README.md`
- `docs/DESIGN.md`
- `docs/SPEC.md`
- `docs/DIALECTS.md`
- `docs/PASSES.md`
- `docs/FRONTENDS.md`
- `docs/BACKENDS.md`
- `docs/CLI.md`
- `docs/DIAGNOSTICS.md`
- `docs/TESTING.md`
- `docs/PROJECT_STRUCTURE.md`
- `docs/ROADMAP.md`
- `docs/STACK.md`

Read these DSL docs:

- `docs/DSL.md`
- `README_DSL_EXTENSION.md`
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

Inspect these built-in DSL specs:

- `dsl/formats/agenttrove.agentir.yaml`
- `dsl/formats/codex_swebenchpro.agentir.yaml`
- `dsl/formats/claude_code.agentir.yaml`
- `dsl/formats/openhands.agentir.yaml`
- `dsl/formats/hermes_agent.agentir.yaml`
- `dsl/templates/minimal_sharegpt.agentir.yaml`
- `dsl/templates/native_tool_jsonl.agentir.yaml`
- `examples/user_defined/react_agent_jsonl.agentir.yaml`

## Hard constraints

1. Preserve existing `src/` and `tests/` behavior unless extending it compatibly.
2. Do not remove handwritten frontends.
3. Add DSL frontends alongside handwritten frontends.
4. Do not bypass IR models, pass manager, verifier, diagnostics, source maps, or backends.
5. Do not use arbitrary Python `eval` or `exec` for DSL evaluation.
6. Do not call external LLM APIs.
7. Preserve raw source rows by default.
8. Every emitted event should carry provenance whenever possible.
9. Every backend lowering should produce or support a loss report.
10. Use Python 3.11+, Pydantic v2, Typer, Rich, and the repository's existing style.

## Implementation sequence

### Phase 0: Baseline audit

Run current tests first. Record what already passes and what fails.

```bash
uv run pytest || pytest
```

Summarize existing structure and identify which docs already match implementation.

### Phase 1: DSL models and validation

Implement or extend:

```text
src/agentir/dsl/models.py
src/agentir/dsl/loader.py
src/agentir/dsl/validator.py
```

Requirements:

- load `*.agentir.yaml` with `ruamel.yaml`;
- validate `apiVersion=agentir.qitor.ai/v0.1`;
- validate `kind=TrajectoryFormat`;
- validate fields from `docs/dsl/DSL_SPEC.md`;
- reject unknown transforms/emitters unless plugin mode is explicitly enabled;
- provide `agentir dsl validate`;
- provide schema export.

Acceptance commands:

```bash
agentir dsl validate dsl/formats/hermes_agent.agentir.yaml
agentir dsl validate dsl/formats/openhands.agentir.yaml
agentir dsl schema export --output schema/agentir.format_dsl.schema.v0.1.json
```

### Phase 2: Selector, expression, condition engine

Implement or extend:

```text
src/agentir/dsl/selectors.py
src/agentir/dsl/expressions.py
src/agentir/dsl/conditions.py
```

Required selectors:

- `$`
- `$.field`
- `$.a.b`
- `$.items[0]`
- `$.items[*]`
- `$.items[*].content`

Required expressions:

- `path`
- `const`
- `template`
- `first_of`
- `default`
- `transform`
- `var`

Required conditions:

- `field_exists`
- `field_nonempty`
- `all`
- `any`
- `equals`

Invalid syntax should return diagnostics, not uncaught exceptions.

### Phase 3: Built-in transforms and emitters

Implement or extend:

```text
src/agentir/dsl/transforms.py
src/agentir/dsl/emitters.py
```

Required transforms include:

- `role_to_event_type`
- `role_to_message_role`
- `role_to_actor_id`
- `parse_json`
- `json_dumps_compact`
- `strip`
- `normalize_whitespace`
- `regex_extract`
- `extract_xml_blocks`
- `parse_tool_call_json`
- `parse_tool_response_json`
- `normalize_tool_name`
- `infer_action_kind`
- `infer_side_effect_level`
- `looks_like_diff`
- `extract_unified_diff`
- `changed_files_from_diff`
- `infer_outcome_status`
- `source_field_for_loop`
- `reasoning_visibility`

Required emitters include at least:

- `message_event`
- `tool_call_event`
- `tool_result_event`
- `artifact_event`
- `outcome`
- `actor`
- `tool_def`

### Phase 4: Runtime DSL frontend

Implement or extend:

```text
src/agentir/dsl/compiler.py
src/agentir/dsl/runtime_frontend.py
src/agentir/frontends/dsl_frontend.py
```

Requirements:

- compile selectors/templates/transforms once per spec;
- detect records according to `detect.rules`;
- build normal `AgentIRRecord` objects;
- preserve raw row;
- emit task, actors, tools, artifacts, episodes, events, and outcome;
- support `foreach`, `emit_once`, `expand_tool_calls`, and optional XML block expansion;
- collect diagnostics.

Acceptance command:

```bash
agentir-as --frontend-dsl dsl/templates/minimal_sharegpt.agentir.yaml \
  --input tests/fixtures/dsl/minimal_sharegpt.jsonl \
  --output tmp/minimal_sharegpt.air.jsonl
```

### Phase 5: CLI and terminal UX

Implement or extend:

```text
src/agentir/cli/dsl_cmd.py
src/agentir/cli/tui_cmd.py
```

Required commands:

- `agentir dsl validate`
- `agentir dsl schema export`
- `agentir dsl init`
- `agentir dsl probe`
- `agentir dsl preview`
- `agentir dsl compile --emit-plan`
- `agentir dsl bench`
- `agentir dsl diff`

Also add:

- `agentir-as --frontend-dsl`
- `agentir compile --frontend-dsl`
- `agentir compile --passes spec:default`

The first terminal UX should use Rich tables/panels. A Textual fullscreen TUI is optional and must gracefully fall back if Textual is not installed.

### Phase 6: Built-in DSL specs and equivalence tests

Ensure these validate and parse fixtures:

```text
dsl/formats/agenttrove.agentir.yaml
dsl/formats/codex_swebenchpro.agentir.yaml
dsl/formats/claude_code.agentir.yaml
dsl/formats/openhands.agentir.yaml
dsl/formats/hermes_agent.agentir.yaml
```

Add equivalence tests comparing DSL output with handwritten frontend output.

```bash
uv run pytest tests/test_dsl_equivalence.py -q
```

### Phase 7: Performance path

Implement streaming and benchmark reporting:

- streaming JSONL reader;
- selector compilation cache;
- transform function registry cache;
- batched emission where possible;
- benchmark metrics: rows/s, events/s, diagnostics/s, peak memory, parse/emit/pass/backend timing;
- optional Parquet/Arrow fast path if existing IO supports it.

Acceptance:

```bash
agentir dsl bench dsl/formats/openhands.agentir.yaml --input tests/fixtures/openhands_sample.jsonl --limit 10000
```

## Completion criteria

The task is complete when:

1. Existing tests pass or all pre-existing failures are documented.
2. New DSL tests pass.
3. All built-in DSL specs validate.
4. All five built-in DSL specs parse fixtures.
5. Equivalence tests pass for DSL vs handwritten frontends.
6. `agentir-as --frontend-dsl` works.
7. `agentir compile --frontend-dsl --passes spec:default` works.
8. `agentir dsl probe`, `preview`, `bench`, and `diff` produce useful terminal output.
9. No unsafe eval/exec/plugin execution happens by default.

## Final report format

Report:

- files added/modified;
- commands run;
- test results;
- any known limitations;
- example commands for adding a new user-defined trajectory format.
