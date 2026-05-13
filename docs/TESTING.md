# Testing and Acceptance Criteria

## Test philosophy

agentir is infrastructure. Tests must verify semantics, not just line coverage.

## Required test structure

```text
tests/
  fixtures/
    agenttrove_sample.jsonl
    codex_swebenchpro_sample.jsonl
    claude_code_sample.jsonl
    openhands_sample.jsonl
    hermes_agent_sample.jsonl
  test_ir_models.py
  test_frontends.py
  test_passes.py
  test_backends.py
  test_cli.py
  test_roundtrip.py
  test_diagnostics.py
```

## Fixture requirements

Claude Code must create synthetic minimal fixtures if live HF loading is unavailable. Fixtures must include:

1. Hermes sample with `<think>`, `<tool_call>`, and `<tool_response>`.
2. OpenHands sample with native `tool_calls` and `model_patch`.
3. Claude Code sample with `messages_json`, `tools_json`, `gitdiff`, and empty assistant case.
4. AgentTrove sample with ShareGPT turns and reward.
5. Codex sample with `conversations: [{from, value}]`.

## Unit tests

### IR model tests

- Construct valid `AgentIRRecord`.
- Serialize and deserialize through JSON.
- Generate JSON Schema.
- Reject invalid enum values.

### Frontend tests

Each frontend must:

- detect correct sample with score > 0.8
- parse sample without fatal error
- preserve raw row
- emit expected number of events
- set expected source fields

### Pass tests

Required:

- `parse-hermes-xml` extracts reasoning/tool call/tool response.
- `pair-tool-results` pairs by ID and adjacency.
- `extract-patches` creates patch artifact.
- `normalize-outcome` maps reward/pass fields.
- `redact-reasoning` applies all policies.
- `verify` catches duplicate event IDs.

### Backend tests

Required:

- SFT backend produces messages list.
- OpenAI tools backend preserves tool calls.
- Hermes XML backend serializes tool calls as XML blocks.
- OpenHands backend emits `trajectory` and `model_patch`.
- ShareGPT backend reports lossy when tool calls exist.

### CLI tests

Use `pytest` tmp paths:

- `agentir-as --input fixture --output out.raw.air.jsonl`
- `agentir-opt out.raw.air.jsonl --passes ...`
- `agentir-llc out.canonical.air.jsonl --target sft ...`
- `agentir verify ...`
- `agentir schema export ...`

## Roundtrip tests

Required roundtrips:

1. Hermes fixture → AgentIR → Hermes XML
2. OpenHands fixture → AgentIR → OpenHands
3. OpenHands fixture → AgentIR → SFT
4. Claude Code fixture → AgentIR → process-supervision

Roundtrip expectations:

- Not all roundtrips need be exact.
- Tests must assert correct `LossReport.status`.
- If lowering is lossy, loss items must explain why.

## Quality gates

Before declaring v0.1 complete:

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest --cov=agentir --cov-report=term-missing
```

Minimum acceptance:

- 80% test coverage for `src/agentir/ir`, `frontends`, `passes`, `backends`.
- No mypy errors in `src/agentir/ir` and `src/agentir/diagnostics`.
- All CLI smoke tests pass.
- JSON Schema export works.

