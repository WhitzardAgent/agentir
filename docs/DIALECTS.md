# AgentIR Dialects

AgentIR Core must stay small. Domain-specific details belong in dialects. A dialect is a typed namespace of event kinds, metadata conventions, and normalization rules.

## Dialect registry

Implement `src/agentir/dialects/registry.py` with:

```python
class DialectSpec(BaseModel):
    name: str
    version: str = "0.1.0"
    event_types: list[str]
    artifact_kinds: list[str] = []
    metadata_schema: dict[str, Any] = {}
```

All dialects must register themselves at import time through a central registry.

## 1. Core dialect: `agent`

Purpose: universal agent trajectory semantics.

Events:

- `system_message`
- `user_message`
- `assistant_message`
- `tool_message`
- `reasoning`
- `plan`
- `todo_update`
- `agent_handoff`
- `subtask_spawn`
- `subtask_result`
- `state_snapshot`
- `finish`
- `error`
- `unparsed_fragment`

Required metadata conventions:

```json
{
  "agent.phase": "setup|understand|plan|inspect|act|repair|verify|finalize|unknown",
  "agent.confidence": 1.0
}
```

## 2. Tool dialect: `tool`

Purpose: normalize function/tool calls across frameworks.

Events:

- `tool_call`
- `tool_result`
- `tool_error`
- `tool_retry`

Metadata:

```json
{
  "tool.name.raw": "execute_bash",
  "tool.name.normalized": "terminal.exec",
  "tool.call_style": "native_tool_call|xml_block|json_in_text|bash_batch|inferred|unknown",
  "tool.call_id": "call_...",
  "tool.schema.available": true
}
```

Normalization rule:

- OpenHands `tool_calls` → `tool_call` with `call_style=native_tool_call`.
- Hermes `<tool_call>` → `tool_call` with `call_style=xml_block`.
- Claude Code embedded assistant tool use → `tool_call` with `call_style=inferred`.
- AgentTrove/Codex JSON action in text → `tool_call` with `call_style=json_in_text`.

## 3. Terminal dialect: `terminal`

Events:

- `terminal_command`
- `terminal_output`

Action rules:

```json
{
  "action.kind": "terminal",
  "action.side_effect_level": "read_only|workspace_write|external_write|network|unknown"
}
```

Side effect inference:

- `ls`, `cat`, `sed -n`, `grep`, `rg`, `pwd` → `read_only`
- `python -m pytest`, `pytest`, `npm test` → `read_only` unless command writes known output
- `touch`, `mkdir`, `rm`, `mv`, `cp`, `python script_that_edits` → `workspace_write` or `unknown`
- `curl`, `wget`, `git clone`, browser fetch → `network`

Do not over-infer. Use `unknown` when unsure.

## 4. File dialect: `file`

Events:

- `file_read`
- `file_write`
- `file_patch`

Artifacts:

- `patch`
- `file`

Patch handling:

- Store final diff as `Artifact(kind=PATCH)`.
- Link patch event to artifact via `artifacts` and `state_delta.patch_artifact_id`.
- For OpenHands `model_patch`, create one final patch artifact.
- For Claude Code `gitdiff`, create one patch artifact and mark provenance source field as `gitdiff`.

## 5. Browser dialect: `browser`

Events:

- `browser_action`
- `browser_observation`

Action kinds:

- `navigate`
- `click`
- `type`
- `extract`
- `screenshot`
- `scroll`

Artifacts:

- `screenshot`
- `webpage`

## 6. SWE dialect: `swe`

Purpose: coding-agent and SWE-bench style tasks.

Task metadata:

```json
{
  "swe.repo": "owner/repo",
  "swe.base_commit": "...",
  "swe.issue_id": "...",
  "swe.benchmark": "swebench|swebenchpro|unknown",
  "swe.dataset": "..."
}
```

Events:

- `file_patch`
- `verification`
- `reward`

Outcome rules:

- If `passed == true`, outcome status is `success` unless conflicting diagnostics exist.
- If `reward > 0` but `passed` is missing, status may be `success` only if dataset semantics define reward that way.
- If `has_empty_response == true` in Claude Code source, emit warning and set failure reason `empty_response` when no better outcome exists.

## 7. Reasoning dialect: `reasoning`

Events:

- `reasoning`
- `plan`
- `critique`
- `repair_note`

Visibility:

Every reasoning event must set:

```json
{
  "visibility.contains_reasoning": true,
  "visibility.trainable": false,
  "visibility.policy": "preserve|summarize|drop|redact|metadata_only"
}
```

Default policy for public exports: `metadata_only`.

## 8. Evaluation dialect: `eval`

Events:

- `verification`
- `reward`

Outcome metadata:

```json
{
  "eval.verifier.type": "swebench|pytest|custom|human|unknown",
  "eval.passed": true,
  "eval.reward": 1.0,
  "eval.failure_reason": "test_failed|timeout|compile_error|empty_response|tool_error|parse_error|unknown"
}
```

## Dialect extension rule

New dialects must not modify core schema. They may add:

- new metadata keys
- frontend-specific parser logic
- backend-specific lowering logic
- analysis pass outputs

Breaking core schema changes require bumping `ir_version`.

