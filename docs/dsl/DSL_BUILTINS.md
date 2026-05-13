# AgentIR DSL Built-ins

This document lists the built-in selector operations, transforms, emitters, and parser primitives required for DSL v0.1.

All built-ins must be deterministic, side-effect free, and safe for streaming conversion.

## Value expression built-ins

### `path`

```yaml
path: $.conversations[*].value
```

Returns selected value(s) from the current scope.

Scope rules:

- `$` points to the source row.
- `context` points to conversion context: row index, dataset, split, input path.
- loop variables such as `turn` point to the current item.
- `item` is used inside mapping contexts.

### `const`

```yaml
const: unknown
```

Returns a literal scalar, list, or dict.

### `template`

```yaml
template: "evt_{i:04d}_call_{j:02d}"
```

Uses a restricted template engine.

Allowed variables:

- loop variables, such as `i`, `j`;
- previously bound vars;
- `context.row_index`;
- `metadata.name`.

No function calls are allowed inside templates.

### `first_of`

```yaml
first_of:
  - path: $.messages
  - path: $.conversations
  - const: []
```

Returns the first value that is present and non-empty unless `allow_empty=true` is set.

### `default`

```yaml
default:
  value: {path: $.score}
  fallback: 0.0
```

Returns fallback when value is missing.

### `transform`

```yaml
transform: parse_json
input: $.tools_json
```

Applies a whitelisted transform.

## Required transforms

### Role transforms

#### `role_to_event_type`

Maps role aliases to AgentIR event types.

Default aliases:

| Source role | Event type |
|---|---|
| `system` | `system_message` |
| `developer` | `system_message` with role `developer` |
| `human` | `user_message` |
| `user` | `user_message` |
| `gpt` | `assistant_message` |
| `assistant` | `assistant_message` |
| `tool` | `tool_message` or `tool_result` depending on context |
| `environment` | `tool_result` or `terminal_output` depending on context |

#### `role_to_message_role`

Maps role aliases to `MessageRole`.

#### `role_to_actor_id`

Maps role aliases to default actors: `system`, `user`, `assistant`, `tool`, `environment`, or `unknown`.

### JSON transforms

#### `parse_json`

Parses a JSON string into a dict/list.

Options:

```yaml
transform: parse_json
input: $.tools_json
on_error: diagnostic
fallback: []
```

#### `json_dumps_compact`

Serializes a value into compact JSON text.

#### `json_get`

Extracts a key from a dict with fallback.


#### `build_messages_from_fields`

Builds a small message list from separate prompt fields. Empty fields are skipped.

Example input:

```yaml
input:
  system: {path: $.system_prompt}
  user: {path: $.user_prompt}
  assistant: {path: $.assistant_response}
```

Output:

```json
[
  {"role":"system","content":"..."},
  {"role":"user","content":"..."},
  {"role":"assistant","content":"..."}
]
```

### Text transforms

#### `strip`

Trims whitespace.

#### `normalize_whitespace`

Collapses repeated whitespace.

#### `regex_extract`

```yaml
transform: regex_extract
input: $.assistant_response
pattern: "```diff\\n(?P<diff>.*?)```"
group: diff
flags: [dotall]
```

Regex must use timeout protection.

#### `text_contains_any`

Returns bool.

### XML/tool block transforms

#### `extract_xml_blocks`

Extracts XML-like blocks from text without unsafe XML parsing.

Supported block names:

- `think`
- `tool_call`
- `tool_response`

The implementation may use a safe scanner instead of a full XML parser because many tool traces are XML-like, not valid XML documents.

#### `parse_tool_call_json`

Parses a tool call block into:

```json
{
  "name": "...",
  "arguments": {},
  "id": "..."
}
```

Accepted shapes:

```json
{"name":"bash","arguments":{"cmd":"ls"}}
{"function":{"name":"bash","arguments":"{...}"},"id":"call_1"}
{"tool_name":"bash","tool_input":{}}
```

#### `parse_tool_response_json`

Parses tool response block into `Observation` content when possible.

### Tool normalization transforms

#### `normalize_tool_name`

Maps common tool aliases into normalized names.

Examples:

| Raw name | Normalized name |
|---|---|
| `bash` | `terminal.exec` |
| `execute_bash` | `terminal.exec` |
| `shell` | `terminal.exec` |
| `str_replace_editor` | `file.edit` |
| `edit_file` | `file.edit` |
| `read_file` | `file.read` |
| `browser.open` | `browser.navigate` |

#### `infer_action_kind`

Maps a normalized tool name to `ActionKind`.

#### `infer_side_effect_level`

For terminal commands and tool names, conservatively infer side effects.

Read-only examples:

- `ls`
- `cat`
- `sed -n`
- `grep`
- `rg`
- `pwd`
- `pytest` unless known to generate files

Write/network examples:

- `touch`, `mkdir`, `rm`, `mv`, `cp` → `workspace_write` or `unknown`
- `curl`, `wget`, `git clone` → `network`

Use `unknown` if unsure.

### Patch transforms

#### `looks_like_diff`

Returns bool for text that resembles unified diff.

#### `extract_unified_diff`

Extracts diff blocks from Markdown or plain text.

#### `changed_files_from_diff`

Returns changed file paths where parseable.

### Outcome transforms

#### `infer_outcome_status`

Inputs may include:

```yaml
input:
  passed: {path: $.passed}
  reward: {path: $.reward}
  status: {path: $.status}
```

Rules:

- `passed=true` → `success`
- `passed=false` → `failure`
- explicit valid status wins unless it conflicts with `passed`, in which case emit `OUTCOME001`
- reward alone must not imply success unless DSL field `outcome.reward_semantics: pass_indicator` is set

## Event emitter built-ins

### `message_event`

Emits message events from role/content fields.

### `native_tool_call_events`

Emits tool call events from native arrays such as OpenAI/OpenHands `tool_calls`.

### `tool_role_result_event`

Converts `role=tool` messages into `tool_result` events.

### `xml_block_events`

Emits events from `<think>`, `<tool_call>`, and `<tool_response>` blocks.

### `patch_event`

Emits `file_patch` event and links patch artifact.

### `terminal_transcript_events`

Extracts terminal commands and outputs from structured or semi-structured logs.

v0.1 only needs simple support. More advanced terminal transcript parsing belongs in later passes.

## Provenance built-ins

### `source_field_for_loop`

```yaml
source_field:
  transform: source_field_for_loop
  input:
    base: conversations
    index: {var: i}
    field: value
```

Produces `conversations[3].value`.

### `char_span_from_regex`

Returns character offsets from a regex match.

### `char_span_from_xml_block`

Returns character offsets for extracted XML-like blocks.

## Policy built-ins

### `reasoning_visibility`

Returns default visibility for reasoning events:

```json
{
  "trainable": false,
  "contains_reasoning": true,
  "redaction_status": "metadata_only",
  "policy": "metadata_only"
}
```

### `public_export_visibility`

Applies default public export policy.

## Built-in predicate names

These can be used in detection and conditions:

- `is_sharegpt_like`
- `has_native_tool_calls`
- `has_hermes_xml_blocks`
- `has_unified_diff`
- `has_claude_code_fields`
- `has_openhands_fields`
- `is_probably_terminal_transcript`

## Safety requirements

Every built-in must follow these constraints:

- no network calls;
- no shell calls;
- no LLM calls;
- bounded input length by default;
- regex timeout and max match count;
- XML parsing must use safe parser or scanner;
- transforms must return diagnostics instead of throwing uncaught exceptions.
