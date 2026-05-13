# Testing AgentIR DSL

The DSL layer is compiler infrastructure. Tests must verify semantics, not only syntax.

## Test structure delta

Add:

```text
tests/
  fixtures/
    dsl/
      minimal_sharegpt.jsonl
      native_tool_jsonl.jsonl
  test_dsl_models.py
  test_dsl_selectors.py
  test_dsl_transforms.py
  test_dsl_runtime_frontend.py
  test_dsl_cli.py
  test_dsl_equivalence.py
  test_dsl_diagnostics.py
```

## DSL model tests

Required:

- load every `dsl/formats/*.agentir.yaml`;
- load every `dsl/templates/*.agentir.yaml`;
- reject missing `metadata.name`;
- reject unknown `apiVersion`;
- reject unknown transform unless plugin mode is enabled;
- reject unsupported selector syntax;
- export DSL JSON Schema.

## Selector tests

Required selectors:

- `$`
- `$.a`
- `$.a.b`
- `$.items[0]`
- `$.items[*]`
- `$.items[*].content`
- missing path returns a typed missing value, not an exception;
- wildcard projection preserves item order.

Add property tests for nested dict/list traversal.

## Transform tests

Required transforms:

- `role_to_event_type`
- `role_to_message_role`
- `role_to_actor_id`
- `parse_json`
- `normalize_tool_name`
- `infer_action_kind`
- `infer_side_effect_level`
- `extract_xml_blocks`
- `parse_tool_call_json`
- `looks_like_diff`
- `extract_unified_diff`
- `infer_outcome_status`
- `reasoning_visibility`

All transform failures must return diagnostics and fallback values, not uncaught exceptions.

## Runtime frontend tests

For a minimal ShareGPT DSL:

- parse record into `AgentIRRecord`;
- preserve raw row;
- emit expected event types;
- attach provenance;
- map actors and task fields;
- emit diagnostics for missing required field.

For native tool JSONL DSL:

- emit assistant message event;
- emit `tool_call` event from native tool call;
- emit `tool_result` event from tool role message;
- pass `canonicalize-tools,pair-tool-results,verify`.

## Equivalence tests for the five representative formats

For each format:

1. parse fixture with hand-written Python frontend;
2. parse same fixture with DSL frontend;
3. normalize both outputs into a semantic snapshot;
4. compare snapshots.

Formats:

- AgentTrove
- Codex SWE-bench Pro
- Claude Code
- OpenHands
- Hermes Agent

Semantic snapshot should include:

```json
{
  "record_id": "...",
  "source.framework": "...",
  "task": {...},
  "tool_registry.names": [...],
  "event_types": [...],
  "roles": [...],
  "tool_calls": [...],
  "artifacts.kind": [...],
  "outcome": {...}
}
```

Do not require exact equality for:

- generated event IDs;
- metadata ordering;
- diagnostic ordering when semantically equivalent;
- provenance char offsets unless explicitly tested.

## CLI tests

Required smoke tests:

```bash
agentir dsl validate dsl/formats/hermes_agent.agentir.yaml
agentir dsl probe dsl/formats/hermes_agent.agentir.yaml --input tests/fixtures/hermes_agent_sample.jsonl --limit 1
agentir dsl preview dsl/formats/hermes_agent.agentir.yaml --input tests/fixtures/hermes_agent_sample.jsonl --limit 1 --show-events
agentir-as --frontend-dsl dsl/formats/hermes_agent.agentir.yaml --input tests/fixtures/hermes_agent_sample.jsonl --output tmp/hermes.dsl.air.jsonl
agentir compile --frontend-dsl dsl/formats/hermes_agent.agentir.yaml --input tests/fixtures/hermes_agent_sample.jsonl --passes spec:default --target sft --output tmp/hermes.sft.jsonl --workdir tmp/hermes_compile
```

## Golden output tests

For each built-in DSL spec, commit small golden snapshots:

```text
tests/golden/dsl/
  hermes_agent.snapshot.json
  openhands.snapshot.json
  claude_code.snapshot.json
  agenttrove.snapshot.json
  codex_swebenchpro.snapshot.json
```

Regenerate with:

```bash
uv run python scripts/update_dsl_golden.py
```

Golden updates require review.

## Diagnostic tests

Ensure these diagnostics are produced:

- invalid DSL field → `DSL001`
- unknown transform → `DSL002`
- missing selected field → `SELECT001` when required
- transform failure → `TRANSFORM001`
- event emission failure → `EMIT001`
- missing provenance in strict mode → `EMIT002`
- plugin transform not allowed → `DSLSEC001`

## Performance tests

Performance tests should not block regular CI unless marked.

Add:

```python
@pytest.mark.perf
```

Minimum manual acceptance:

- runtime frontend streams 10k JSONL rows without accumulating records;
- `agentir dsl bench` completes and reports stage timings;
- no obvious O(n^2) behavior for message arrays.

## TUI tests

Do not require full Textual integration in normal CI.

Test:

- `agentir tui` prints helpful fallback when Textual is missing;
- non-interactive commands produce expected Rich-free output under non-TTY mode;
- preview and probe can emit JSON reports for snapshot testing.

## Quality gates

Before declaring DSL v0.1 complete:

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest tests/test_dsl_*.py -q
uv run pytest tests/test_cli.py tests/test_roundtrip.py -q
```

Acceptance:

- all built-in DSL specs validate;
- five representative DSL specs parse fixtures;
- DSL and Python frontend snapshots match semantically;
- DSL CLI commands have smoke tests;
- no unsafe eval or plugin execution in default tests.
