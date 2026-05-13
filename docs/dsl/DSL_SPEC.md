# AgentIR Format DSL v0.1 Specification

This document defines the YAML DSL used to describe trajectory source formats.

The DSL is intentionally declarative. It must be implemented with Pydantic v2 models under `src/agentir/dsl/` and validated before any source data is parsed.

## Top-level object

```yaml
apiVersion: agentir.qitor.ai/v0.1
kind: TrajectoryFormat
metadata: {}
source: {}
detect: {}
vars: {}
actors: []
tool_registry: {}
task: {}
artifacts: []
episodes: []
outcome: {}
passes: []
quality: {}
performance: {}
```

Required fields:

- `apiVersion`
- `kind`
- `metadata.name`
- `source`
- at least one `episodes[*].events` rule

## `apiVersion`

Must be:

```yaml
apiVersion: agentir.qitor.ai/v0.1
```

This is the DSL version, not the AgentIR version.

## `kind`

Must be:

```yaml
kind: TrajectoryFormat
```

Future kinds may include `TransformLibrary`, `DialectExtension`, and `BackendProjection`, but v0.1 only requires `TrajectoryFormat`.

## `metadata`

```yaml
metadata:
  name: hermes-agent
  title: Hermes Agent Reasoning Traces
  version: 0.1.0
  description: ShareGPT-style conversations with Hermes XML tool blocks.
  owners: [agentir]
  tags: [sharegpt, tools, reasoning, xml]
```

Rules:

- `metadata.name` is the stable frontend name.
- Use lowercase kebab-case.
- Built-in DSL frontends should not conflict with hand-written frontend names unless they intentionally implement equivalent behavior.

## `source`

```yaml
source:
  kind: jsonl
  record_mode: row
  default_dataset: lambda/hermes-agent-reasoning-traces
  default_split: train
  format: sharegpt+xml-tools
  framework: hermes-agent
  raw_policy: full
```

Fields:

| Field | Meaning |
|---|---|
| `kind` | `json`, `jsonl`, `parquet`, `hf`, or `unknown` |
| `record_mode` | `row`, `array`, or `auto` |
| `default_dataset` | optional dataset ID |
| `default_config` | optional HF config |
| `default_split` | optional split |
| `format` | source format string stored in `SourceRef.format` |
| `framework` | source framework stored in `SourceRef.framework` |
| `license` | optional source license |
| `raw_policy` | `full`, `external_ref`, `hash_only`, or `none_for_tests_only` |

`raw_policy=full` is the default and required for built-in specs. `hash_only` is not allowed unless the user explicitly passes `--allow-raw-hash-only`.


## `source_overrides`

`source` stores static defaults. `source_overrides` maps row-specific fields into `SourceRef`.

```yaml
source_overrides:
  row_id: {path: $.trajectory_id}
  license: {path: $.license}
  original_source: {path: $.original_source}
  original_teacher: {path: $.original_teacher}
```

Supported keys mirror `SourceRef` fields: `dataset`, `dataset_url`, `config`, `split`, `row_id`, `framework`, `framework_version`, `format`, `license`, `original_source`, and `original_teacher`.

Overrides are value expressions and should be evaluated after `source` defaults and `FrontendContext` values. CLI context values such as `--hf-dataset` should still take priority over static defaults unless the override is row-specific, such as `row_id` or `license`.

## `detect`

`detect` controls format auto-detection and `agentir dsl probe`.

```yaml
detect:
  min_score: 0.70
  rules:
    - field_exists: $.conversations
      score: 0.40
    - field_is_list: $.conversations
      score: 0.20
    - any_field_exists: [$.tools, $.tools_json]
      score: 0.10
    - text_contains:
        path: $.conversations[*].value
        any: ["<tool_call>", "<think>"]
      score: 0.30
```

Supported rule types:

- `field_exists`
- `field_missing`
- `field_is_list`
- `field_is_dict`
- `field_is_string`
- `any_field_exists`
- `all_fields_exist`
- `text_contains`
- `regex_match`
- `json_parseable`
- `sample_predicate` using a whitelisted predicate from `DSL_BUILTINS.md`

Rules add scores. Detection score is clipped to `[0, 1]`.

## `vars`

`vars` defines reusable named values.

```yaml
vars:
  turns:
    first_of:
      - path: $.messages
      - path: $.conversations
      - path: $.conversation
      - const: []
  row_id:
    first_of:
      - path: $.trajectory_id
      - path: $.id
      - template: "row_{context.row_index}"
```

Supported value expressions:

- `path`
- `const`
- `template`
- `first_of`
- `transform`
- `map`
- `filter`
- `default`

Value expressions are not Python code. They are evaluated by the DSL runtime.

## Path expressions

Use a restricted JSONPath-like syntax:

```text
$                         whole row
$.field                   object field
$.a.b                     nested field
$.items[0]                list index
$.items[*]                list wildcard
$.items[*].content        wildcard projection
```

Unsupported in v0.1:

- arbitrary script expressions;
- recursive descent (`..`);
- arithmetic inside selectors;
- method calls.

The selector engine must compile selectors once per spec and reuse them for all records.

## `actors`

```yaml
actors:
  - actor_id: system
    kind: system
    name: System
  - actor_id: user
    kind: user
    name: User
  - actor_id: assistant
    kind: assistant
    name: Assistant
    model:
      first_of:
        - path: $.model
        - path: $.metadata.model
```

Actor fields map directly to `ActorSpec`.

## `tool_registry`

```yaml
tool_registry:
  from:
    first_of:
      - path: $.tools
      - transform: parse_json
        input: $.tools_json
      - const: []
  item:
    name:
      first_of:
        - path: item.name
        - path: item.function.name
    description:
      first_of:
        - path: item.description
        - path: item.function.description
    input_schema:
      first_of:
        - path: item.input_schema
        - path: item.parameters
        - path: item.function.parameters
        - const: {}
```

Rules:

- `from` must evaluate to a list, dict, JSON string, or empty value.
- If the value is a JSON string, `parse_json` must be explicit unless `auto_parse_json_strings=true` is set.
- Tool IDs are generated stably as `tool_{normalized_name}` unless provided.

## `task`

```yaml
task:
  task_id:
    first_of: [{path: $.task_id}, {path: $.run_id}]
  instruction:
    first_of:
      - path: $.task
      - path: $.instruction
      - path: $.prompt
      - path: $.conversations[0].value
  category: {path: $.category}
  subcategory: {path: $.subcategory}
  benchmark: {path: $.benchmark}
  repo:
    first_of: [{path: $.repo}, {path: $.repository}]
  base_commit: {path: $.base_commit}
  issue_id:
    first_of: [{path: $.issue_id}, {path: $.instance_id}]
  environment:
    kind: {const: unknown}
    cwd: {path: $.cwd}
    network: {const: unknown}
```

Every field is optional unless the DSL spec marks it required through `quality.required_fields`.

## `artifacts`

Artifacts can be emitted from direct fields or transforms.

```yaml
artifacts:
  - when:
      field_nonempty: $.model_patch
    artifact_id: final_patch
    kind: patch
    content: {path: $.model_patch}
    mime_type: text/x-diff
    created_by_event_id: evt_final_patch
    provenance:
      source_field: model_patch
```

Supported artifact fields map to `Artifact`:

- `artifact_id`
- `kind`
- `uri`
- `path`
- `content`
- `encoding`
- `mime_type`
- `sha256`
- `size_bytes`
- `created_by_event_id`
- `metadata`
- `provenance` for source-map generation

## `episodes`

Most records contain one episode.

```yaml
episodes:
  - episode_id:
      first_of:
        - path: $.trajectory_id
        - path: $.run_id
        - template: "episode_{context.row_index}"
    task_id: {var: task.task_id}
    events: []
```

`events` is a list of event emission rules.

## Event emission rules

### `foreach` rule

```yaml
- foreach: {var: turns}
  as: turn
  index_as: i
  emit:
    event_id: {template: "evt_{i:04d}"}
    idx: {var: i}
    event_type:
      transform: role_to_event_type
      input:
        first_of:
          - path: turn.role
          - path: turn.from
    role:
      transform: role_to_message_role
      input:
        first_of:
          - path: turn.role
          - path: turn.from
    actor_id:
      transform: role_to_actor_id
      input:
        first_of:
          - path: turn.role
          - path: turn.from
    content:
      - type: text
        text:
          first_of:
            - path: turn.content
            - path: turn.value
            - const: ""
    provenance:
      source_field: {template: "conversations[{i}]"}
```

### `emit_once` rule

```yaml
- emit_once:
    when:
      field_nonempty: $.gitdiff
    event_id: evt_gitdiff
    idx: auto
    event_type: file_patch
    actor_id: assistant
    content:
      - type: diff
        text: {path: $.gitdiff}
    artifacts: [gitdiff_patch]
```

### `expand_tool_calls` rule

```yaml
- foreach: {var: turns}
  as: turn
  index_as: i
  expand_tool_calls:
    from: turn.tool_calls
    parent_event_id: {template: "evt_{i:04d}"}
    event_id_template: "evt_{i:04d}_call_{j:02d}"
```

This is shorthand for emitting `tool_call` events from native tool call arrays.

### `expand_xml_blocks` rule

```yaml
- foreach: {var: turns}
  as: turn
  index_as: i
  expand_xml_blocks:
    source: turn.value
    blocks: [think, tool_call, tool_response]
    parent_event_id: {template: "evt_{i:04d}"}
```

This is optional. Built-in specs may prefer to emit message events and then run parser passes such as `parse-hermes-xml`.

## `outcome`

```yaml
outcome:
  reward:
    first_of:
      - path: $.reward
      - path: $.score
  passed:
    first_of:
      - path: $.passed
      - path: $.success
  status:
    transform: infer_outcome_status
    input:
      passed: {path: $.passed}
      reward: {path: $.reward}
  final_answer:
    first_of:
      - path: $.final_answer
      - path: $.assistant_response
  final_patch_artifact_id:
    when:
      field_nonempty: $.model_patch
    const: final_patch
```

Outcome inference must be conservative. If source semantics are unknown, emit reward but leave status as `unknown`.

## `passes`

Default passes to run after DSL parsing.

```yaml
passes:
  default:
    - canonicalize-tools
    - pair-tool-results
    - extract-patches
    - normalize-outcome
    - verify
  recommended_for_training:
    - canonicalize-tools
    - pair-tool-results
    - extract-patches
    - normalize-outcome
    - redact-reasoning
    - slice-training
    - verify
```

The CLI may override pass pipelines.

## `quality`

```yaml
quality:
  required_fields:
    - $.conversations
  warn_if_empty:
    - path: $.assistant_response
      code: DATA001
      message: assistant_response is empty
  min_events: 1
  require_provenance: true
  strict_tool_pairing: false
```

Used by `agentir dsl validate`, `agentir dsl probe`, and verifier pre-checks.

## `performance`

```yaml
performance:
  selector_cache: true
  transform_cache: true
  preferred_batch_size: 1024
  streaming_safe: true
  can_generate_python: true
```

These are hints. The runtime may ignore them if unsafe.

## Condition syntax

Supported conditions:

```yaml
when:
  field_exists: $.model_patch

when:
  field_nonempty: $.assistant_response

when:
  all:
    - field_exists: $.trajectory
    - field_nonempty: $.trajectory

when:
  any:
    - field_exists: $.messages
    - field_exists: $.conversations

when:
  equals:
    left: {path: turn.role}
    right: assistant
```

Unsupported in v0.1:

- arbitrary Python lambdas;
- shell commands;
- network calls;
- LLM calls.

## Error behavior

The DSL runtime must never crash on a malformed source row unless `--strict` is set.

Instead, it must emit diagnostics:

- DSL schema error: `DSL001`
- selector failed: `SELECT001`
- transform failed: `TRANSFORM001`
- event emission failed: `EMIT001`
- provenance missing: `EMIT002`
- source data issue: existing `DATA*` codes

## Serialization

The DSL spec itself should be normalized by:

```bash
agentir dsl format formats/my_format.agentir.yaml
```

Rules:

- preserve comments when possible through `ruamel.yaml`;
- sort top-level fields in canonical order;
- do not rewrite user strings;
- do not expand shorthand unless `--expand` is passed.
