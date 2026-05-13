# Pass System

agentir must implement a compiler-style pass manager.

## Pass interface

```python
class PassKind(str, Enum):
    PARSE = "parse"
    CANONICALIZE = "canonicalize"
    ANALYSIS = "analysis"
    TRANSFORM = "transform"
    VERIFY = "verify"
    LOWERING_PREP = "lowering_prep"

class PassResult(BaseModel):
    record: AgentIRRecord
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    analysis: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)

class AgentIRPass(Protocol):
    name: str
    kind: PassKind
    def run(self, record: AgentIRRecord, ctx: PassContext) -> PassResult: ...
```

## Pass manager

Implement:

```python
class PassManager:
    def __init__(self, registry: PassRegistry): ...
    def run_pipeline(self, record: AgentIRRecord, passes: list[str], ctx: PassContext) -> PassResult: ...
```

Pipeline syntax:

```bash
--passes parse-hermes-xml,canonicalize-tools,pair-tool-results,normalize-outcome,verify
```

## Required passes for v0.1

### 1. `parse-hermes-xml`

Input: events containing Hermes-style XML blocks in content.

Parse:

- `<think>...</think>` → `reasoning`
- `<tool_call>{...}</tool_call>` → `tool_call`
- `<tool_response>{...}</tool_response>` → `tool_result`

Rules:

- Use `defusedxml` or safe custom parser. Never use unsafe XML parsing.
- Preserve original text event.
- Add parsed events after the source message event unless a frontend already emitted parsed events.
- Set provenance char ranges when possible.
- If malformed XML, emit `PARSE001` warning and create `unparsed_fragment`.

### 2. `parse-sharegpt`

Input: raw conversation rows using role/content or from/value.

Rules:

- Normalize role names: `human` → user, `gpt` → assistant, `tool` → tool.
- Convert each turn into a message event.
- Do not infer tool calls unless enabled by `--infer-tools`.

### 3. `parse-claude-log`

Input: Claude Code `claude_log`, `messages_json`, `tools_json`, `assistant_response`.

Rules:

- Prefer `messages_json` as primary structure.
- Parse `tools_json` into `tool_registry`.
- If `gitdiff` exists, create patch artifact.
- If assistant response is empty, emit `DATA001` warning.
- Tool calls embedded in assistant response must be marked `call_style=inferred` and confidence <= 0.7.

### 4. `parse-openhands-tool-calls`

Input: OpenHands `trajectory` list.

Rules:

- Structured `tool_calls` become `tool_call` events with confidence 1.0.
- Tool role messages become `tool_result` events.
- Preserve original messages.
- `model_patch` becomes final patch artifact.

### 5. `canonicalize-tools`

Normalize tool calls into `Action`.

Rules:

- Every `tool_call` gets `Action(kind=GENERIC_TOOL)` unless a more specific kind is known.
- Terminal-like tools map to `Action(kind=TERMINAL)`.
- File-edit tools map to file action kinds.
- Browser tools map to `Action(kind=BROWSER)`.
- Preserve raw tool name under metadata.

### 6. `pair-tool-results`

Pair tool calls with results.

Rules:

- Exact match by `tool_call_id` first.
- Then adjacent tool result after tool call.
- Then source framework-specific fields.
- If no match, emit `PAIR001` warning.
- If result without call, emit `PAIR002` warning.
- Do not invent IDs without marking provenance confidence < 1.0.

### 7. `extract-patches`

Extract diffs into patch artifacts.

Sources:

- OpenHands `model_patch`
- Claude Code `gitdiff`
- assistant content containing unified diff blocks

Rules:

- Use `unidiff` when possible.
- If parse succeeds, add changed file paths to state delta.
- If parse fails but text looks like diff, still store as patch artifact with `PARSE002`.

### 8. `normalize-outcome`

Normalize rewards and pass/fail markers.

Rules:

- AgentTrove `reward` maps to `Outcome.reward`.
- OpenHands success metadata, if available, maps to `Outcome.passed`.
- Codex SWE-bench trial stats, if available, map to `VerifierResult`.
- Claude Code `has_empty_response` may map to `FailureReason.EMPTY_RESPONSE`.
- If reward and passed conflict, emit `OUTCOME001`.

### 9. `redact-reasoning`

Apply reasoning policy.

CLI options:

```bash
--reasoning-policy preserve|summarize|drop|redact|metadata_only
```

Rules:

- Default public export policy: `metadata_only`.
- `drop`: remove reasoning events from trainable projections, not from raw record.
- `redact`: keep event with placeholder `[REDACTED_REASONING]`.
- `metadata_only`: remove content but preserve provenance and existence.
- `summarize`: v0.1 may use placeholder `[REASONING_SUMMARY_NOT_IMPLEMENTED]`; do not call LLM.

### 10. `slice-training`

Create trainable projections.

Rules:

- Drop non-trainable events unless backend requests them.
- Merge adjacent user/assistant message events when safe.
- Keep tool_call/tool_result adjacency.
- Preserve metadata needed for attribution.

### 11. `verify`

Run verifier checks.

Default checks:

- Unique event IDs inside each episode.
- Monotonic event indices.
- Valid parent IDs.
- Tool calls have names.
- Tool results should match calls when possible.
- Artifacts referenced by events exist.
- Outcome status/reward/passed conflicts are reported.
- Reasoning events have visibility policy.

Strict mode additionally fails on:

- missing provenance for parsed events
- unknown tool result pairing
- malformed patch artifact
- empty assistant message without explicit incomplete diagnostic

## Analysis passes for v0.2

Not required for v0.1, but design must allow:

- `state-flow-analysis`
- `artifact-dependency-analysis`
- `failure-mode-analysis`
- `trainability-analysis`
- `tool-curriculum-analysis`
- `trajectory-quality-scoring`

