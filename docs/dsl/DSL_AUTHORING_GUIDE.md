# Authoring a New AgentIR Format DSL

This guide is written for users who want to ingest a new agent trajectory dataset into AgentIR without writing Python.

## Authoring target

A good DSL spec should answer these questions:

1. How do I recognize this format?
2. Where are the turns/events?
3. How are roles represented?
4. Where are tool calls and tool results?
5. Where are terminal commands, browser actions, file edits, and patches?
6. Where are task metadata and outcomes?
7. Which events are inferred and therefore low confidence?
8. Which normal AgentIR passes should run after parsing?

## Minimal example

```yaml
apiVersion: agentir.qitor.ai/v0.1
kind: TrajectoryFormat
metadata:
  name: my-sharegpt
  version: 0.1.0
source:
  kind: jsonl
  record_mode: row
  framework: custom
  format: sharegpt
  raw_policy: full
detect:
  min_score: 0.7
  rules:
    - field_exists: $.conversations
      score: 0.5
    - field_is_list: $.conversations
      score: 0.2
vars:
  turns: {path: $.conversations}
actors:
  - actor_id: user
    kind: user
  - actor_id: assistant
    kind: assistant
episodes:
  - episode_id: {template: "episode_{context.row_index}"}
    events:
      - foreach: {var: turns}
        as: turn
        index_as: i
        emit:
          event_id: {template: "evt_{i:04d}"}
          idx: {var: i}
          event_type:
            transform: role_to_event_type
            input: {path: turn.from}
          role:
            transform: role_to_message_role
            input: {path: turn.from}
          actor_id:
            transform: role_to_actor_id
            input: {path: turn.from}
          content:
            - type: text
              text: {path: turn.value}
          provenance:
            source_field: {template: "conversations[{i}].value"}
passes:
  default: [canonicalize-tools, pair-tool-results, normalize-outcome, verify]
```

## Step-by-step workflow

### 1. Inspect sample records

```bash
agentir inspect samples/my_trace.jsonl --limit 3
```

or use the DSL probe command after creating a draft spec:

```bash
agentir dsl probe formats/my_trace.agentir.yaml --input samples/my_trace.jsonl --limit 10
```

Look for:

- top-level fields;
- message arrays;
- role/content keys;
- tool call structures;
- tool result structures;
- outcome fields;
- repo/task identifiers;
- patch/diff fields.

### 2. Write detection rules

A good detector should be specific but cheap.

Good:

```yaml
detect:
  min_score: 0.75
  rules:
    - field_exists: $.trajectory
      score: 0.4
    - field_is_list: $.trajectory
      score: 0.2
    - any_field_exists: [$.model_patch, $.repo, $.trajectory_id]
      score: 0.2
```

Avoid expensive detection:

```yaml
# Avoid scanning massive logs in detection unless bounded.
- regex_match:
    path: $.huge_log
    pattern: "..."
```

### 3. Bind reusable variables

Use `vars` for repeated paths and fallbacks.

```yaml
vars:
  turns:
    first_of:
      - path: $.trajectory
      - path: $.messages
      - path: $.conversations
      - const: []
  row_id:
    first_of:
      - path: $.trajectory_id
      - path: $.id
      - template: "row_{context.row_index}"
```

### 4. Define actors

At minimum define system/user/assistant. Add tool/environment if the format has tool results.

```yaml
actors:
  - actor_id: system
    kind: system
  - actor_id: user
    kind: user
  - actor_id: assistant
    kind: assistant
  - actor_id: tool
    kind: tool
  - actor_id: environment
    kind: environment
```

### 5. Map messages

Use role transforms rather than hard-coded event types when possible.

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
        first_of: [{path: turn.role}, {path: turn.from}]
    role:
      transform: role_to_message_role
      input:
        first_of: [{path: turn.role}, {path: turn.from}]
    content:
      - type: text
        text:
          first_of: [{path: turn.content}, {path: turn.value}, {const: ""}]
```

### 6. Preserve native tool calls

For OpenAI/OpenHands-style tool calls:

```yaml
- foreach: {var: turns}
  as: turn
  index_as: i
  expand_tool_calls:
    from: turn.tool_calls
    parent_event_id: {template: "evt_{i:04d}"}
    event_id_template: "evt_{i:04d}_call_{j:02d}"
```

### 7. Convert tool-role messages into tool results

If `role=tool` messages contain results, either let `role_to_event_type` map them or add explicit rule:

```yaml
- foreach: {var: turns}
  as: turn
  index_as: i
  when:
    equals:
      left: {path: turn.role}
      right: tool
  emit:
    event_id: {template: "evt_{i:04d}_result"}
    idx: auto
    event_type: tool_result
    actor_id: tool
    observation:
      kind: tool_json
      content:
        - type: text
          text: {path: turn.content}
```

### 8. Handle reasoning safely

For `<think>` blocks or other reasoning text, prefer parser passes when the format is already supported:

```yaml
passes:
  default: [parse-hermes-xml, canonicalize-tools, pair-tool-results, redact-reasoning, verify]
```

If the DSL directly emits reasoning events, set visibility:

```yaml
visibility:
  transform: reasoning_visibility
```

### 9. Emit artifacts

For patches:

```yaml
artifacts:
  - when:
      field_nonempty: $.model_patch
    artifact_id: final_patch
    kind: patch
    content: {path: $.model_patch}
    mime_type: text/x-diff
    provenance:
      source_field: model_patch
```

Then emit an event linked to the artifact:

```yaml
- emit_once:
    when:
      field_nonempty: $.model_patch
    event_id: evt_final_patch
    idx: auto
    event_type: file_patch
    actor_id: assistant
    content:
      - type: diff
        text: {path: $.model_patch}
    artifacts: [final_patch]
```

### 10. Map outcomes conservatively

```yaml
outcome:
  reward: {path: $.reward}
  passed: {path: $.passed}
  status:
    transform: infer_outcome_status
    input:
      passed: {path: $.passed}
      reward: {path: $.reward}
```

Do not infer `success` from reward unless dataset semantics are explicit.

### 11. Validate and preview

```bash
agentir dsl validate formats/my_trace.agentir.yaml
agentir dsl preview formats/my_trace.agentir.yaml --input samples/my_trace.jsonl --limit 5 --show-events
```

Check:

- event count;
- event order;
- roles;
- tool call IDs;
- tool/result pairing after passes;
- artifacts;
- outcome;
- diagnostics.

### 12. Benchmark before large conversion

```bash
agentir dsl bench formats/my_trace.agentir.yaml --input samples/my_trace.jsonl --limit 10000
```

If conversion is slow:

- avoid expensive regex transforms in event loops;
- use native structured fields over parsing text;
- compile to generated Python frontend;
- increase batch size for Parquet;
- use `--jobs` for sharded JSONL input.

## Quality checklist

Before contributing a DSL spec:

- [ ] `agentir dsl validate` passes.
- [ ] `agentir dsl probe` detects the format with score ≥ `min_score`.
- [ ] `agentir dsl preview` emits expected events.
- [ ] All parsed events have provenance when possible.
- [ ] Tool calls preserve IDs and arguments.
- [ ] Tool results pair with calls after `pair-tool-results`.
- [ ] Artifacts are linked by ID, not copied into every event.
- [ ] Reasoning has visibility policy.
- [ ] Outcome does not overclaim success.
- [ ] Golden tests exist.
- [ ] Loss report from at least one backend is understandable.
