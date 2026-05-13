# Backends and Lowering Targets

Backends lower canonical AgentIR into target formats. They must not silently drop semantics. Every backend produces a `LossReport`.

## Backend API

```python
class LoweringStatus(str, Enum):
    EXACT = "exact"
    LOSSY = "lossy"
    PARTIAL = "partial"
    UNSUPPORTED = "unsupported"

class LossItem(BaseModel):
    severity: DiagnosticSeverity
    code: str
    field: str | None = None
    message: str
    event_id: str | None = None
    suggestion: str | None = None

class LossReport(BaseModel):
    target: str
    status: LoweringStatus
    losses: list[LossItem] = []
    metrics: dict[str, Any] = {}

class LoweringResult(BaseModel):
    output: Any
    report: LossReport

class Backend(Protocol):
    name: str
    def lower_record(self, record: AgentIRRecord, ctx: BackendContext) -> LoweringResult: ...
```

## Required backends v0.1

### 1. SFT backend: `sft`

Output shape:

```json
{
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "...", "tool_calls": []},
    {"role": "tool", "tool_call_id": "...", "content": "..."}
  ],
  "metadata": {
    "trajectory_id": "...",
    "source_dataset": "...",
    "source_framework": "...",
    "reward": 1.0,
    "passed": true
  }
}
```

Rules:

- Drop reasoning events by default unless `--include-reasoning` is set.
- Preserve tool calls when target model format supports them.
- Tool result must follow corresponding tool call when possible.
- If a target SFT record has no assistant output, emit loss warning.

### 2. Process supervision backend: `process-supervision`

Output shape:

```json
{
  "trajectory_id": "...",
  "steps": [
    {
      "step_id": "evt_0010",
      "state": {...},
      "action": {...},
      "observation": {...},
      "label": {
        "is_progress": null,
        "failure_type": null
      }
    }
  ],
  "outcome": {...},
  "metadata": {...}
}
```

Rules:

- Each `tool_call`, `terminal_command`, `file_write`, `file_patch`, `browser_action` becomes a step.
- Attach nearest following observation/tool result.
- Include outcome at trajectory level.
- Do not fabricate progress labels in v0.1; set null unless source provides labels.

### 3. OpenAI tools backend: `openai-tools`

Output shape follows the common chat messages + `tool_calls` style.

Rules:

- Convert assistant tool calls into assistant message with `tool_calls`.
- Convert tool results into role `tool` messages with `tool_call_id`.
- Reasoning events are dropped by default.
- If a tool call lacks ID, generate stable ID `call_<event_id>` and report loss item `LOWER001`.

### 4. Hermes XML backend: `hermes-xml`

Output shape:

```json
{
  "conversations": [
    {"from": "system", "value": "..."},
    {"from": "human", "value": "..."},
    {"from": "gpt", "value": "<think>...</think>\n<tool_call>{...}</tool_call>"},
    {"from": "tool", "value": "<tool_response>{...}</tool_response>"}
  ],
  "tools": "[...]"
}
```

Rules:

- Include reasoning only if policy permits.
- Escape invalid XML-sensitive text.
- Tool call arguments must be valid JSON inside `<tool_call>`.
- If target cannot represent multi-artifact observations, report lossy.

### 5. OpenHands backend: `openhands`

Output shape:

```json
{
  "trajectory_id": "...",
  "repo": "...",
  "trajectory": [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "...", "tool_calls": [...]},
    {"role": "tool", "content": "...", "tool_call_id": "..."}
  ],
  "model_patch": "diff --git ..."
}
```

Rules:

- Prefer structured native tool calls.
- Patch artifacts become `model_patch` when available.
- If non-coding artifacts cannot be represented, report lossy.

### 6. ShareGPT backend: `sharegpt`

Output shape:

```json
{
  "conversations": [
    {"from": "human", "value": "..."},
    {"from": "gpt", "value": "..."}
  ],
  "metadata": {...}
}
```

Rules:

- This is inherently lossy for structured tool calls.
- Tool calls may be serialized into text only when `--tool-policy inline`.
- Default status should often be `lossy` or `partial`.

## v0.2+ backends

- `anthropic-tools`
- `rl-rollout`
- `dpo`
- `swe-patch-view`
- `otel`
- `openinference`

Design interfaces now, but implementation may wait unless trivial.

## Loss report markdown

For every lowering command with `--loss-report`, emit Markdown:

```markdown
# Loss Report

Target: openhands  
Status: lossy

## Summary

- Records processed: 1000
- Exact: 812
- Lossy: 150
- Partial: 38
- Unsupported: 0

## Losses

### warning LOWER003

Field: reasoning  
Event: evt_0019  
Message: Target format cannot represent private reasoning blocks.  
Suggestion: Use `--reasoning-policy drop` or `metadata_only`.
```

