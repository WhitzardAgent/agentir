# Project Structure Delta for DSL Support

This document extends `docs/PROJECT_STRUCTURE.md`.

## Add to repository root

```text
agentir/
  README_DSL_EXTENSION.md

  dsl/
    formats/
      agenttrove.agentir.yaml
      codex_swebenchpro.agentir.yaml
      claude_code.agentir.yaml
      openhands.agentir.yaml
      hermes_agent.agentir.yaml
    templates/
      minimal_sharegpt.agentir.yaml
      native_tool_jsonl.agentir.yaml

  examples/
    user_defined/
      react_agent_jsonl.agentir.yaml

  docs/
    dsl/
      DSL_OVERVIEW.md
      DSL_SPEC.md
      DSL_BUILTINS.md
      DSL_RUNTIME.md
      DSL_AUTHORING_GUIDE.md
      DSL_CLI_DELTA.md
      DSL_TERMINAL_UI.md
      DSL_PERFORMANCE.md
      DSL_TESTING.md
      DSL_SECURITY.md
      DSL_DIAGNOSTICS_DELTA.md
      DSL_PROJECT_STRUCTURE_DELTA.md
      DSL_ROADMAP.md

  schema/
    agentir.format_dsl.schema.v0.1.json  # generated, not hand-written
    format_dsl.schema.v0.1.note.md
```

## Add to `src/agentir/`

```text
src/agentir/
  dsl/
    __init__.py
    models.py
    loader.py
    validator.py
    selectors.py
    expressions.py
    transforms.py
    conditions.py
    emitters.py
    compiler.py
    runtime_frontend.py
    codegen.py
    reports.py
    bench.py
    tui.py

  frontends/
    dsl_frontend.py
    generated/
      __init__.py

  cli/
    dsl_cmd.py
    tui_cmd.py
```

## Add to tests

```text
tests/
  fixtures/
    dsl/
      minimal_sharegpt.jsonl
      native_tool_jsonl.jsonl
  golden/
    dsl/
      agenttrove.snapshot.json
      codex_swebenchpro.snapshot.json
      claude_code.snapshot.json
      openhands.snapshot.json
      hermes_agent.snapshot.json
  test_dsl_models.py
  test_dsl_selectors.py
  test_dsl_transforms.py
  test_dsl_runtime_frontend.py
  test_dsl_cli.py
  test_dsl_equivalence.py
  test_dsl_diagnostics.py
```

## Dependency delta

Add to `pyproject.toml`:

```toml
dependencies = [
  "ruamel.yaml>=0.18",
]

[project.optional-dependencies]
tui = [
  "textual>=0.70",
]
perf = [
  "duckdb>=1.0",
  "ijson>=3.3",
]
```

Do not make Textual required for core CLI usage.

## Script entry points

Existing `agentir` umbrella command should include `dsl` and `tui` subcommands.

No separate console script is required for `agentir-dslc`, but it is acceptable to add one later as an alias:

```toml
agentir-dslc = "agentir.cli.dsl_cmd:app"
```
