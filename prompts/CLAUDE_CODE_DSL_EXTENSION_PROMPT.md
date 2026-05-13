# Claude Code Prompt: Implement AgentIR Format DSL Extension

You are Claude Code working in the existing `agentir` repository.

Your job is implementation. Do not redesign the architecture. Implement the DSL extension described by this package while preserving all existing v0.1 AgentIR compiler abstractions.

## Read first

Read the original core docs:

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

Then read the DSL extension docs:

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

Also inspect the built-in DSL specs:

- `dsl/formats/agenttrove.agentir.yaml`
- `dsl/formats/codex_swebenchpro.agentir.yaml`
- `dsl/formats/claude_code.agentir.yaml`
- `dsl/formats/openhands.agentir.yaml`
- `dsl/formats/hermes_agent.agentir.yaml`
- `dsl/templates/minimal_sharegpt.agentir.yaml`
- `dsl/templates/native_tool_jsonl.agentir.yaml`
- `examples/user_defined/react_agent_jsonl.agentir.yaml`

## Mission

Implement a declarative DSL layer so users can define new agent trajectory source formats through `*.agentir.yaml`, then convert them through the existing AgentIR pipeline.

The goal is to make AgentIR the LLVM for agent trajectories:

```text
source trace format
  ↓ DSL-defined frontend
Parsed AgentIR
  ↓ existing pass manager
Canonical AgentIR
  ↓ existing backends
training / evaluation / replay / observability targets
```

## Hard constraints

1. Do not remove or weaken existing hand-written frontends.
2. Do not bypass AgentIR IR models, pass manager, verifier, diagnostics, or backends.
3. Do not use arbitrary Python `eval` or `exec` in DSL evaluation.
4. Do not allow plugin transforms unless explicitly enabled through CLI.
5. Do not call external LLM APIs.
6. Preserve raw source rows by default.
7. Every parsed event emitted by the DSL should have provenance when possible.
8. Built-in DSL specs must validate and parse fixtures.
9. Existing tests must continue to pass.
10. Use Python 3.11+, Pydantic v2, Typer, Rich, and existing project style.

## Implementation phases

### Phase DSL-1: Repository structure and dependencies

Add files described in `docs/dsl/DSL_PROJECT_STRUCTURE_DELTA.md`.

Add dependency:

- `ruamel.yaml>=0.18`

Add optional dependency group:

- `tui = ["textual>=0.70"]`

Do not require Textual for core tests.

Acceptance:

```bash
uv sync --extra dev
uv run ruff format .
uv run ruff check .
uv run pytest
```

### Phase DSL-2: DSL Pydantic models and YAML loader

Implement:

- `src/agentir/dsl/models.py`
- `src/agentir/dsl/loader.py`
- `src/agentir/dsl/validator.py`

Requirements:

- load `*.agentir.yaml` with `ruamel.yaml`;
- validate `apiVersion=agentir.qitor.ai/v0.1`;
- validate `kind=TrajectoryFormat`;
- validate top-level fields from `docs/dsl/DSL_SPEC.md`;
- reject unknown transforms/emitters unless plugin mode is enabled;
- implement `agentir dsl validate`;
- implement `agentir dsl schema export --output schema/agentir.format_dsl.schema.v0.1.json`.

Acceptance:

```bash
agentir dsl validate dsl/formats/hermes_agent.agentir.yaml
agentir dsl validate dsl/formats/openhands.agentir.yaml
agentir dsl schema export --output schema/agentir.format_dsl.schema.v0.1.json
```

### Phase DSL-3: Selector and expression engine

Implement:

- `src/agentir/dsl/selectors.py`
- `src/agentir/dsl/expressions.py`
- `src/agentir/dsl/conditions.py`

Required selector syntax:

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

Acceptance:

- selector unit tests pass;
- missing optional selectors return a typed missing value;
- invalid selector syntax emits `SELECT003`.

### Phase DSL-4: Built-in transforms

Implement `src/agentir/dsl/transforms.py`.

Required transforms:

- `role_to_event_type`
- `role_to_message_role`
- `role_to_actor_id`
- `parse_json`
- `json_dumps_compact`
- `strip`
- `normalize_whitespace`
- `regex_extract` with timeout/limits
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

Acceptance:

- transform unit tests pass;
- transform errors produce diagnostics, not uncaught exceptions.

### Phase DSL-5: Runtime compiler and frontend

Implement:

- `src/agentir/dsl/compiler.py`
- `src/agentir/dsl/emitters.py`
- `src/agentir/dsl/runtime_frontend.py`
- `src/agentir/frontends/dsl_frontend.py`

Requirements:

- compile selectors/templates/transforms once per spec;
- detect records according to `detect.rules`;
- build normal `AgentIRRecord` objects;
- populate `SourceRef`;
- preserve raw row;
- emit actors, tools, task, artifacts, episodes, events, outcome;
- attach provenance;
- collect diagnostics;
- support event rules: `foreach`, `emit_once`, `expand_tool_calls`, optional `expand_xml_blocks`.

Acceptance:

```bash
agentir-as --frontend-dsl dsl/templates/minimal_sharegpt.agentir.yaml \
  --input tests/fixtures/dsl/minimal_sharegpt.jsonl \
  --output tmp/minimal_sharegpt.air.jsonl
```

### Phase DSL-6: CLI integration

Implement `src/agentir/cli/dsl_cmd.py` and wire into `agentir` umbrella CLI.

Required commands:

- `agentir dsl validate`
- `agentir dsl schema export`
- `agentir dsl init`
- `agentir dsl probe`
- `agentir dsl preview`
- `agentir dsl compile --emit-plan`
- `agentir dsl bench`
- `agentir dsl diff`

Also update:

- `agentir-as --frontend-dsl`
- `agentir compile --frontend-dsl`
- `agentir compile --passes spec:default`

Acceptance:

```bash
agentir dsl probe dsl/formats/hermes_agent.agentir.yaml --input tests/fixtures/hermes_agent_sample.jsonl --limit 1
agentir dsl preview dsl/formats/hermes_agent.agentir.yaml --input tests/fixtures/hermes_agent_sample.jsonl --limit 1 --show-events
```

### Phase DSL-7: Built-in DSL specs and equivalence tests

Make these specs validate and parse fixtures:

- `dsl/formats/agenttrove.agentir.yaml`
- `dsl/formats/codex_swebenchpro.agentir.yaml`
- `dsl/formats/claude_code.agentir.yaml`
- `dsl/formats/openhands.agentir.yaml`
- `dsl/formats/hermes_agent.agentir.yaml`

Implement semantic equivalence tests against hand-written frontends.

Acceptance:

```bash
uv run pytest tests/test_dsl_equivalence.py -q
```

### Phase DSL-8: Terminal UI and performance reporting

Implement non-fullscreen Rich UX first:

- detection rule tables;
- field coverage tables;
- event preview tables;
- diagnostic summaries;
- benchmark tables.

Implement optional `agentir tui` only if time permits. If Textual is missing, print `TUI001` and provide non-fullscreen alternatives.

Acceptance:

```bash
agentir dsl bench dsl/formats/openhands.agentir.yaml --input tests/fixtures/openhands_sample.jsonl --limit 10
agentir tui dsl/formats/openhands.agentir.yaml --input tests/fixtures/openhands_sample.jsonl
```

`agentir tui` may gracefully fall back if Textual is not installed.

## Completion criteria

The DSL extension is complete when:

1. Existing v0.1 AgentIR tests still pass.
2. DSL model/selector/transform/runtime/CLI tests pass.
3. All built-in DSL specs validate.
4. All five built-in DSL specs parse fixtures.
5. Equivalence tests pass against hand-written frontends.
6. `agentir-as --frontend-dsl` works.
7. `agentir compile --frontend-dsl --passes spec:default` works.
8. `agentir dsl probe`, `preview`, and `bench` provide useful Rich output.
9. No unsafe eval/exec/plugin execution happens by default.

## Final report format

When done, report:

- files added/modified;
- commands run;
- test results;
- any known limitations;
- example commands users can run to define and convert a new format.
