# DSL Security and Sandboxing

AgentIR will ingest arbitrary public and private trajectory data. The DSL runtime must be safe by default.

## Core rule

A DSL file is data, not executable code.

The runtime must not execute arbitrary Python, shell commands, network calls, or LLM calls from a DSL spec.

## Prohibited by default

- Python `eval` / `exec`
- shell commands
- network access
- dynamic imports from DSL strings
- arbitrary Jinja expressions
- unbounded regex over huge strings
- unsafe XML parsers
- writing files from transforms
- reading files referenced by source rows unless explicitly supported and sandboxed

## Allowed by default

- restricted path selectors;
- restricted templates;
- whitelisted transforms;
- safe XML-like block scanner;
- JSON parsing with size limits;
- regex with timeout and max input length;
- deterministic normalization functions.

## Plugin transforms

Plugin transforms are useful but risky.

Default behavior:

```text
Plugin transforms are disabled.
```

Enable explicitly:

```bash
agentir-as --frontend-dsl formats/custom.agentir.yaml \
  --allow-plugin-transform my_package.transforms:parse_custom_event
```

Requirements:

- each plugin must be named in CLI;
- plugin import path must match DSL spec reference;
- record plugin name/version in output metadata;
- plugin exceptions become diagnostics;
- plugin transforms are never allowed in built-in specs.

## Regex safety

Regex transforms must support:

- max input bytes;
- timeout;
- max matches;
- diagnostic on timeout.

Suggested defaults:

```text
max_regex_input_bytes = 1_000_000
regex_timeout_ms = 100
max_regex_matches = 10_000
```

## XML safety

Agent traces often contain XML-like blocks that are not valid XML. Do not use unsafe XML parsing.

Allowed approaches:

- use `defusedxml` for valid XML fragments;
- use a bounded scanner for known block tags like `<think>`, `<tool_call>`, `<tool_response>`.

Never allow external entity expansion.

## JSON safety

`parse_json` should support:

- max input bytes;
- clear diagnostic on malformed JSON;
- fallback value;
- no object hook that constructs arbitrary classes.

## Path traversal

If future DSL versions support loading artifacts from paths, enforce:

- explicit base directory;
- no `..` path traversal;
- no symlink escape unless explicitly allowed;
- max file size.

v0.1 should not read arbitrary external files during DSL parsing.

## Denial-of-service protections

The runtime should have configurable limits:

```text
--max-row-bytes
--max-events-per-record
--max-content-bytes-per-event
--max-diagnostics-per-record
--max-regex-input-bytes
--max-json-parse-bytes
```

If a limit is exceeded:

- emit diagnostic;
- truncate or skip the expensive parse depending on policy;
- preserve raw source when possible;
- do not crash unless strict mode is enabled.

## Sensitive data

The DSL should allow marking fields as sensitive:

```yaml
quality:
  sensitive_fields:
    - $.api_key
    - $.secrets[*]
```

Behavior:

- mark corresponding events/content with `visibility.contains_sensitive=true`;
- allow redaction pass to remove sensitive content;
- do not print sensitive values in probe/preview unless `--show-sensitive` is explicitly passed.

## Terminal UI safety

TUI should not print full raw rows containing sensitive fields by default if `quality.sensitive_fields` is configured.

Provide:

```bash
agentir tui SPEC --input DATA --show-sensitive
```

only when the user explicitly asks.

## Supply-chain safety

Built-in DSL specs should be reviewed like code because they define data transformation semantics.

Commit rules:

- no plugin transforms in built-ins;
- no external URLs executed during parsing;
- no target-specific training output directly from DSL;
- tests for malformed input and resource limits.
