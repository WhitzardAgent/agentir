# AgentIR DSL Runtime Design

## Components

Implement the DSL layer under `src/agentir/dsl/`.

```text
src/agentir/dsl/
  __init__.py
  models.py             # Pydantic DSL schema
  loader.py             # YAML loading and normalization
  validator.py          # structural validation and semantic checks
  selectors.py          # compiled selector engine
  expressions.py        # value expression evaluator
  transforms.py         # built-in transform registry
  conditions.py         # condition evaluator
  emitters.py           # AgentIR event/artifact/tool emitters
  compiler.py           # DSL spec → ExtractorPlan/EmitterPlan
  runtime_frontend.py   # RuntimeDSLFrontend
  codegen.py            # optional generated Python frontend
  tui.py                # terminal UI helpers if Textual is enabled
```

## Runtime pipeline

```text
load YAML spec
  ↓
Pydantic validation
  ↓
semantic validation
  ↓
compile selectors and templates
  ↓
build ExtractorPlan + EmitterPlan
  ↓
RuntimeDSLFrontend.parse_record(row, ctx)
  ↓
AgentIRRecord(level=parsed)
```

## Main classes

### `TrajectoryFormatSpec`

Top-level Pydantic model for `*.agentir.yaml`.

It should include:

- `api_version`
- `kind`
- `metadata`
- `source`
- `detect`
- `vars`
- `actors`
- `tool_registry`
- `task`
- `artifacts`
- `episodes`
- `outcome`
- `passes`
- `quality`
- `performance`

### `DSLCompiler`

```python
class DSLCompiler:
    def compile(self, spec: TrajectoryFormatSpec) -> CompiledFormat:
        ...
```

Responsibilities:

- validate spec compatibility with current AgentIR version;
- compile all selectors into selector objects;
- compile templates into template objects;
- resolve built-in transforms;
- reject unknown transforms unless a trusted plugin is enabled;
- build detection plan;
- build event emission plan;
- precompute static actor/tool/task mappings where possible.

### `CompiledFormat`

```python
class CompiledFormat(BaseModel):
    spec: TrajectoryFormatSpec
    detection_plan: DetectionPlan
    extractor_plan: ExtractorPlan
    emitter_plan: EmitterPlan
    default_passes: list[str]
    metrics: dict[str, Any] = {}
```

### `RuntimeDSLFrontend`

```python
class RuntimeDSLFrontend(BaseFrontend):
    def __init__(self, compiled: CompiledFormat): ...
    def detect(self, sample: Mapping[str, Any]) -> float: ...
    def parse_record(self, sample: Mapping[str, Any], ctx: FrontendContext) -> FrontendResult: ...
```

This frontend must return normal `AgentIRRecord` objects.

## Detection behavior

Detection is record-local and fast.

Requirements:

- no transform with unbounded cost may run in detection;
- JSON parse checks must have max byte limits;
- detection should short-circuit when max possible score is below `min_score`;
- `agentir dsl probe` should report why a sample matched or failed.

## SourceRef construction

Every DSL frontend must populate:

```python
SourceRef(
    dataset=ctx.dataset or spec.source.default_dataset,
    config=ctx.config or spec.source.default_config,
    split=ctx.split or spec.source.default_split,
    row_index=ctx.row_index,
    framework=spec.source.framework,
    format=spec.source.format,
    license=spec.source.license,
)
```

`row_id` should come from the DSL if possible, otherwise from row index.

## Raw preservation

Default:

```python
record.raw = {"record": original_row}
```

For very large rows, a future `external_ref` policy may store raw data in sidecar files, but v0.1 should keep `full` as the default and built-in policy.

## Event ID strategy

Event IDs must be stable across repeated conversions of the same row.

Recommended default:

```text
evt_{idx:04d}
evt_{idx:04d}_call_{j:02d}
evt_{idx:04d}_result_{j:02d}
```

If a source has stable event IDs or tool call IDs, preserve them in metadata and use them when safe.

## Provenance generation

For every event emitted from a source field, set:

```python
Provenance(
    dataset=source.dataset,
    config=source.config,
    split=source.split,
    row_id=source.row_id,
    row_index=source.row_index,
    source_field="conversations[3].value",
    parser="dsl:<metadata.name>",
    confidence=1.0,
)
```

For inferred events:

- set `confidence < 1.0`;
- set `metadata.inferred=true`;
- emit diagnostic if confidence is below `quality.min_confidence`.

## Diagnostics behavior

Runtime errors should become diagnostics on the returned record.

Examples:

- missing field but optional → warning or info depending on spec;
- missing required field → error in strict mode, warning otherwise;
- transform failure → `TRANSFORM001`;
- event emission failure → `EMIT001`;
- missing provenance → `EMIT002`;
- DSL spec mismatch → `DSL001` before runtime.

## Pass integration

`agentir-as --frontend-dsl` should only emit RawIR/ParsedIR.

`agentir compile --frontend-dsl` may run the spec's default passes unless the user overrides:

```bash
agentir compile --frontend-dsl formats/my.agentir.yaml --passes spec:default
agentir compile --frontend-dsl formats/my.agentir.yaml --passes canonicalize-tools,pair-tool-results,verify
```

## Optional code generation

`agentir dsl compile --emit-python` generates a Python frontend equivalent to the DSL runtime plan.

Generated code must:

- include a header that it is generated;
- avoid dynamic YAML evaluation at runtime;
- use precompiled selectors and direct field access where possible;
- include golden tests generated from sample rows;
- preserve behavior parity with runtime mode.

## Plugin transforms

Custom transforms are not enabled by default.

To use them:

```bash
agentir-as --frontend-dsl formats/custom.agentir.yaml --allow-plugin-transform my_package.transforms:foo
```

Requirements:

- plugin transform must be explicitly enabled by CLI;
- plugin name and version should be recorded in `record.metadata.dsl.plugins`;
- plugin exceptions must become diagnostics;
- plugins must not be used in built-in specs.

## Compatibility with hand-written frontends

For the five v0.1 formats, implement both:

1. hand-written Python frontend, as specified in the original docs;
2. equivalent DSL spec under `dsl/formats/`.

Add equivalence tests:

```text
fixture → Python frontend → normalized AgentIR snapshot
fixture → DSL frontend    → normalized AgentIR snapshot
assert semantically equivalent
```

Exact JSON equality is not required because event IDs or metadata may differ, but event types, roles, content, tools, artifacts, task fields, and outcome fields must match.
