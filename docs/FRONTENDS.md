# Frontends v0.1

Frontends parse source dataset records into RawIR or ParsedIR. They must not perform all normalization themselves. Use passes for canonicalization.

## Common frontend API

```python
class FrontendContext(BaseModel):
    dataset: str | None = None
    dataset_url: str | None = None
    config: str | None = None
    split: str | None = None
    row_index: int | None = None
    strict: bool = False

class FrontendResult(BaseModel):
    record: AgentIRRecord | None = None
    diagnostics: list[Diagnostic] = []

class BaseFrontend(ABC):
    name: str
    def detect(self, sample: Mapping[str, Any]) -> float: ...
    def parse_record(self, sample: Mapping[str, Any], ctx: FrontendContext) -> FrontendResult: ...
```

## 1. AgentTrove frontend: `agenttrove`

Dataset URL:

`https://huggingface.co/datasets/open-thoughts/AgentTrove`

Known characteristics:

- Large merged dataset.
- ShareGPT-like messages/conversations.
- Metadata may include `original_source`, `original_teacher`, `reward`, `task_id`, `run_id`, `model`, etc.
- Some rows are weakly structured and tool calls may be embedded in text.

Required behavior:

1. Detect fields among `messages`, `conversations`, `conversation`.
2. Convert each turn to message events.
3. Normalize role aliases:
   - `human` → `user_message`
   - `user` → `user_message`
   - `gpt` → `assistant_message`
   - `assistant` → `assistant_message`
   - `system` → `system_message`
   - `tool` → `tool_message`
4. Set `source.dataset = "open-thoughts/AgentTrove"` when loaded by HF command.
5. Map `original_source` and `original_teacher` to `SourceRef`.
6. Map `reward` to `Outcome.reward` but do not infer success unless documented by source metadata.
7. Preserve full source row under `raw.record`.
8. Do not aggressively infer tool calls by default. Tool inference must be opt-in with `--infer-tools`.

Output level: `parsed`.

## 2. Codex SWE-bench Pro frontend: `codex-swebenchpro`

Dataset URL:

`https://huggingface.co/datasets/Inferact/codex_swebenchpro_traces`

Known characteristics:

- ShareGPT-like conversation records.
- Typical field: `conversations: [{from, value}]`.
- Coding/SWE task context may be embedded in text rather than separate fields.

Required behavior:

1. Parse `conversations` into message events.
2. Preserve long assistant logs as content blocks; do not truncate unless CLI asks.
3. If repo/issue metadata exists, populate `TaskSpec.repo`, `TaskSpec.issue_id`, and `TaskSpec.benchmark`.
4. If pass/fail/verifier fields exist, map them into `Outcome`.
5. Store unsupported trial metrics under `metadata.codex.*`.
6. Preserve raw row.

Output level: `parsed`.

## 3. Claude Code frontend: `claude-code`

Dataset URL:

`https://huggingface.co/datasets/nlile/misc-merged-claude-code-traces-v1`

Known fields:

- `messages_json`
- `system_prompt`
- `user_prompt`
- `assistant_response`
- `tools_json`
- `gitdiff`
- `claude_log`
- `chatml`
- possible incomplete/empty assistant response fields

Required behavior:

1. Prefer `messages_json` if parseable.
2. If `messages_json` missing or invalid, fall back to `system_prompt`, `user_prompt`, `assistant_response`.
3. Parse `tools_json` into `ToolSpec` entries.
4. Store `gitdiff` as `Artifact(kind=PATCH)` and create a `file_patch` event.
5. Store `claude_log` as `Artifact(kind=TERMINAL_LOG)` or metadata if too small.
6. Mark empty assistant responses with diagnostic `DATA001`.
7. Embedded tool use must be marked `call_style=inferred` and low confidence.
8. Preserve full raw row.

Output level: `parsed`.

## 4. OpenHands frontend: `openhands`

Dataset URL:

`https://huggingface.co/datasets/nvidia/SWE-Hero-openhands-trajectories`

Known fields:

- `trajectory`: list of messages
- message fields include `role`, `content`, and often `tool_calls`
- `trajectory_id`
- `repo`
- `license`
- `dataset`
- `model_patch`

Required behavior:

1. Create `record_id` from `trajectory_id` when available.
2. Set `TaskSpec.repo` from `repo`.
3. Set `SourceRef.license` from `license`.
4. Convert every trajectory message to message event.
5. Convert each structured `tool_calls` entry into `tool_call` event with:
   - `call_style=native_tool_call`
   - `confidence=1.0`
   - `tool_call_id` from source ID
6. Convert tool role messages into `tool_result` events.
7. Store `model_patch` as final patch artifact.
8. If patch exists, set `Outcome.final_patch_artifact_id`.
9. Preserve raw row.

Output level: `parsed`, often close to canonical after passes.

## 5. Hermes Agent frontend: `hermes-agent`

Dataset URL:

`https://huggingface.co/datasets/lambda/hermes-agent-reasoning-traces`

Known fields:

- `conversations`: ShareGPT-like list using `from` and `value`
- `tools`: JSON string or JSON object containing tool definitions
- `category`
- `subcategory`
- `task`
- message content may contain:
  - `<think>...</think>`
  - `<tool_call>...</tool_call>`
  - `<tool_response>...</tool_response>`

Required behavior:

1. Parse `conversations` into message events.
2. Parse `tools` into `ToolSpec` entries.
3. Set `TaskSpec.category`, `TaskSpec.subcategory`, and `TaskSpec.instruction` from source fields when present.
4. Do not parse XML directly in frontend unless implementing a thin extraction helper; the required parser is `parse-hermes-xml` pass.
5. If frontend does parse XML, it must still be idempotent with the pass.
6. Reasoning content from `<think>` must become `reasoning` event with `visibility.contains_reasoning=true` and default policy `metadata_only` for public export.
7. Preserve raw row.

Output level: `parsed`.

## HF loading command behavior

Implement:

```bash
agentir-as --frontend hermes-agent --hf-dataset lambda/hermes-agent-reasoning-traces --split train --limit 1000 --output out/hermes.raw.air.jsonl
```

Options:

- `--hf-dataset`
- `--config`
- `--split`
- `--streaming / --no-streaming`
- `--limit`
- `--output`
- `--format jsonl|parquet`
- `--strict`

## Local loading behavior

Implement local input:

```bash
agentir-as --frontend openhands --input samples/openhands.jsonl --output out/openhands.raw.air.jsonl
agentir-as --frontend openhands --input samples/openhands.parquet --output out/openhands.raw.air.jsonl
```

Supported local input formats v0.1:

- `.json`
- `.jsonl`
- `.parquet`

