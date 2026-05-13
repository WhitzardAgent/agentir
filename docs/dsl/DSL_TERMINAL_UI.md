# Terminal UI for AgentIR DSL Authoring and Conversion

AgentIR should have excellent terminal UX. The DSL layer will fail if users must edit YAML blindly.

The terminal UI should support both simple Rich-based commands and an optional full-screen Textual app.

## UX goals

1. Help users understand unfamiliar trace formats quickly.
2. Make DSL authoring iterative and sample-driven.
3. Show source row → DSL bindings → AgentIR events → diagnostics in one workflow.
4. Surface conversion throughput and bottlenecks.
5. Keep the CLI useful over SSH and in server environments.

## Required non-fullscreen commands

These must work without Textual:

```bash
agentir dsl probe SPEC --input DATA
agentir dsl preview SPEC --input DATA
agentir dsl bench SPEC --input DATA
agentir dsl diff --dsl SPEC --frontend NAME --input DATA
```

Use Rich tables, progress bars, trees, and syntax-highlighted JSON/YAML.

## Optional full-screen TUI

Command:

```bash
agentir tui SPEC --input DATA
```

Optional dependency group:

```toml
[project.optional-dependencies]
tui = ["textual>=0.70", "textual-dev>=1.5"]
```

If Textual is not installed, show a helpful message and fall back to `agentir dsl preview` suggestions.

## TUI layout

Recommended panels:

```text
┌────────────────────────────── AgentIR DSL TUI ──────────────────────────────┐
│ Spec: hermes_agent.agentir.yaml  Input: hermes.jsonl  Row: 12/1000          │
├────────────── Source Row ───────────────┬────────────── Bindings ───────────┤
│ JSON tree / raw text                    │ vars.turns: list[6]              │
│ highlighted selected fields             │ task.instruction: ...            │
│                                          │ tool_registry: 3 tools           │
├────────────── Emitted Events ───────────┼────────────── Diagnostics ────────┤
│ idx event_type actor tool/content        │ warning[PAIR001] ...             │
│ 0   user_message user ...                │ info[DSL...] ...                 │
│ 1   assistant_message assistant ...      │                                  │
├────────────── Pass Preview ─────────────┴────────────── Performance ────────┤
│ parse-hermes-xml → canonicalize-tools → pair-tool-results → verify          │
│ records/s, events/s, selector ms, transform ms, memory                      │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Core interactions

### Navigation

- `j` / `down`: next row
- `k` / `up`: previous row
- `g`: go to row
- `/`: search in source row
- `n`: next search hit
- `N`: previous search hit

### Views

- `1`: source row
- `2`: bindings
- `3`: emitted events
- `4`: diagnostics
- `5`: pass preview
- `6`: performance
- `tab`: cycle panels

### DSL authoring helpers

- `p`: copy selected field path
- `e`: open external editor at spec location if terminal supports it
- `r`: reload spec from disk
- `v`: validate spec
- `b`: run benchmark on current input slice
- `d`: diff against registered Python frontend if provided

### Event inspection

Selecting an event should show:

- full `Event` JSON;
- content blocks;
- action/observation;
- artifacts;
- provenance;
- raw source fragment if available;
- diagnostics linked to this event.

## Probe output requirements

`agentir dsl probe` should show:

```text
Detection summary
┏━━━━━━┳━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Row  ┃ Score ┃ Matched rules                      ┃
┣━━━━━━╋━━━━━━━╋━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫
┃ 0    ┃ 0.93  ┃ $.conversations, $.tools, <think>  ┃
┃ 1    ┃ 0.88  ┃ $.conversations, $.tools           ┃
┗━━━━━━┻━━━━━━━┻━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
```

Field coverage:

```text
Field coverage
┏━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━━━━┓
┃ Field / selector       ┃ Found  ┃ Empty / Missing┃
┣━━━━━━━━━━━━━━━━━━━━━━━╋━━━━━━━━╋━━━━━━━━━━━━━━━┫
┃ $.conversations        ┃ 20/20  ┃ 0/20          ┃
┃ $.tools                ┃ 18/20  ┃ 2/20          ┃
┃ $.model_patch          ┃ 4/20   ┃ 16/20         ┃
┗━━━━━━━━━━━━━━━━━━━━━━━┻━━━━━━━━┻━━━━━━━━━━━━━━━┛
```

## Preview output requirements

`agentir dsl preview --show-events` should show:

```text
Events for row 0
┏━━━━━┳━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━┓
┃ idx ┃ event_type       ┃ actor     ┃ tool         ┃ summary              ┃
┣━━━━━╋━━━━━━━━━━━━━━━━━━╋━━━━━━━━━━━╋━━━━━━━━━━━━━━╋━━━━━━━━━━━━━━━━━━━━━━┫
┃ 0   ┃ user_message     ┃ user      ┃              ┃ Fix failing test...  ┃
┃ 1   ┃ assistant_message┃ assistant ┃              ┃ I will inspect...    ┃
┃ 2   ┃ tool_call        ┃ assistant ┃ terminal.exec┃ pytest -q            ┃
┃ 3   ┃ tool_result      ┃ tool      ┃              ┃ exit_code=1          ┃
┗━━━━━┻━━━━━━━━━━━━━━━━━━┻━━━━━━━━━━━┻━━━━━━━━━━━━━━┻━━━━━━━━━━━━━━━━━━━━━━┛
```

## Conversion progress UI

`agentir-as` and `agentir compile` should show streaming progress for large jobs:

```text
Converting traces.jsonl with dsl/formats/openhands.agentir.yaml
Records: 1,240,000 | 32,400 rec/s | 210 MB/s | Errors: 0 | Warnings: 421
Current stage: emit_events | Slowest transform: parse_json($.tools_json)
```

Do not print per-record diagnostics for huge jobs by default. Aggregate and sample them, while keeping full diagnostics in output records or reports.

## Diagnostic drill-down

For repeated diagnostics, group by code and source field:

```text
Diagnostics summary
┏━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Code       ┃ Severity ┃ Count  ┃ Top source field                   ┃
┣━━━━━━━━━━━━╋━━━━━━━━━━╋━━━━━━━━╋━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫
┃ DATA001    ┃ warning  ┃ 421    ┃ assistant_response                 ┃
┃ PAIR001    ┃ warning  ┃ 37     ┃ trajectory[*].tool_calls           ┃
┃ SELECT001  ┃ warning  ┃ 9      ┃ tools_json                         ┃
┗━━━━━━━━━━━━┻━━━━━━━━━━┻━━━━━━━━┻━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
```

## Authoring ergonomics

TUI should be able to generate YAML snippets:

- selected field path → `path: $.foo.bar`;
- selected array → `foreach` scaffold;
- detected role/content pair → message event scaffold;
- native tool call array → `expand_tool_calls` scaffold;
- patch-looking field → artifact + `file_patch` scaffold.

The TUI does not need to edit YAML in v0.1, but it should make copying correct snippets easy.

## Accessibility and server compatibility

- All commands must work in non-interactive mode.
- Full-screen TUI must be optional.
- Rich output should degrade cleanly when `NO_COLOR` or non-TTY output is detected.
- Every TUI feature should have a CLI equivalent.
