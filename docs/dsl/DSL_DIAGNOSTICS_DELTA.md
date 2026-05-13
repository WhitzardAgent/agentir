# Diagnostics Delta for AgentIR DSL

This document extends `docs/DIAGNOSTICS.md` with DSL-specific diagnostic codes.

## New code namespaces

| Prefix | Area |
|---|---|
| `DSL` | DSL schema and semantic validation |
| `SELECT` | path selector evaluation |
| `TRANSFORM` | transform execution |
| `EMIT` | AgentIR object emission |
| `DSLSEC` | DSL security and plugin policy |
| `PERF` | performance warnings |
| `TUI` | terminal UI issues |

## Required codes

| Code | Severity | Meaning |
|---|---|---|
| `DSL001` | error | DSL schema validation failed |
| `DSL002` | error | unknown transform or emitter |
| `DSL003` | warning | DSL spec uses deprecated field |
| `DSL004` | warning | detection rules are too weak or always match |
| `SELECT001` | warning | selector path missing for optional field |
| `SELECT002` | error | selector path missing for required field |
| `SELECT003` | error | unsupported selector syntax |
| `TRANSFORM001` | warning | transform failed and fallback was used |
| `TRANSFORM002` | error | transform failed without fallback in strict mode |
| `TRANSFORM003` | warning | regex or parser timeout |
| `EMIT001` | error | event emission failed |
| `EMIT002` | warning | emitted parsed event lacks provenance |
| `EMIT003` | warning | emitted record has zero events |
| `DSLSEC001` | error | plugin transform referenced but not explicitly allowed |
| `DSLSEC002` | error | unsafe expression or operation rejected |
| `PERF001` | warning | expensive transform used in detection or tight loop |
| `PERF002` | warning | source row exceeds recommended size limit |
| `TUI001` | info | Textual not installed; full-screen TUI unavailable |

## Human-readable examples

```text
error[DSL002]: unknown transform 'parse_my_private_log'
  --> formats/my_format.agentir.yaml:42:14
   |
42 |   transform: parse_my_private_log
   |              ^^^^^^^^^^^^^^^^^^^^
   |
help: use a built-in transform, or pass --allow-plugin-transform package.module:parse_my_private_log
```

```text
warning[SELECT001]: optional selector did not match any value
  --> dsl/formats/claude_code.agentir.yaml:27
   |
27 |   path: $.messages_json
   |         ^^^^^^^^^^^^^^^
   |
source: row 18 in samples/claude_code.jsonl
help: this is allowed because a fallback is configured
```

```text
warning[PERF001]: expensive regex transform is used inside an event loop
  --> formats/my_format.agentir.yaml:88
   |
88 | transform: regex_extract
   |            ^^^^^^^^^^^^^
   |
help: move this transform outside the loop with vars, or prefer a structured source field
```

## JSON report

`agentir dsl validate --schema-report report.json` should emit:

```json
{
  "spec": "dsl/formats/hermes_agent.agentir.yaml",
  "valid": true,
  "diagnostics": [],
  "stats": {
    "selectors": 18,
    "transforms": 9,
    "event_rules": 3
  }
}
```
