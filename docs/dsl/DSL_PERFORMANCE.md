# DSL Conversion Performance

AgentIR must be useful for large trajectory corpora. The DSL runtime should be optimized from day one.

## Performance goals

The exact numbers depend on data shape, but the architecture should support:

- streaming JSONL conversion without loading the full dataset into memory;
- Parquet/Arrow batch conversion for columnar datasets;
- selector compilation once per spec;
- transform dispatch caching;
- bounded diagnostics memory;
- optional multiprocessing for sharded inputs;
- optional generated Python frontend for hot formats.

## Processing modes

### Streaming JSONL mode

Default for `.jsonl` and HF streaming.

```text
open input
  → read one row
  → parse JSON with orjson
  → DSL frontend emits AgentIRRecord
  → write output record immediately
```

Memory should stay roughly constant with dataset size.

### Batch mode

Default for `.parquet` and optionally JSONL with `--batch-size`.

```text
read batch
  → compile vector-friendly selectors where possible
  → emit records
  → write Arrow/Parquet row group
```

Batch mode can improve throughput but must not change semantics.

### Generated frontend mode

For stable formats:

```bash
agentir dsl compile SPEC --emit-python src/agentir/frontends/generated/my_format.py
```

Generated frontends can replace generic selector dispatch with direct field access.

## Hot path design

The runtime hot path should avoid:

- reparsing YAML per record;
- recompiling selectors per record;
- repeated Pydantic validation of intermediate expression nodes;
- expensive regex over large strings unless required;
- deep copying source rows repeatedly;
- storing all diagnostics globally.

Recommended internal plan:

```text
TrajectoryFormatSpec
  ↓ compile once
CompiledFormat
  - compiled selectors
  - compiled templates
  - resolved transform callables
  - event emitter closures
  - static actors
  - static source defaults
```

## Selector optimization

Selector engine requirements:

1. Parse and compile selectors once.
2. Use direct Python dict/list traversal for common paths.
3. Support wildcard projection with iterators.
4. Avoid general-purpose JSONPath evaluation in hot loops where simple paths suffice.
5. Track missing paths without raising exceptions.

Example:

```text
$.conversations[*].value
```

should compile into a small traversal plan:

```text
field("conversations") → each() → field("value")
```

## Transform optimization

Transforms should declare cost hints:

```python
class TransformSpec(BaseModel):
    name: str
    deterministic: bool = True
    cacheable: bool = False
    cost: Literal["cheap", "medium", "expensive"] = "cheap"
```

Cache only when safe and useful. For example:

- `normalize_tool_name`: cacheable;
- `role_to_event_type`: cacheable;
- `parse_json`: maybe cacheable for repeated identical strings;
- `regex_extract` over huge logs: not globally cacheable by default.

## Pydantic overhead

Full Pydantic validation per event may be expensive.

Recommended approach:

- validate DSL spec strictly at load time;
- construct AgentIR Pydantic models normally in v0.1 for correctness;
- add `--fast-unsafe-skip-event-validation` only in future after golden tests and schema validation exist;
- for Parquet output, serialize with `model_dump(mode="json", exclude_none=True)` and orjson.

Do not sacrifice correctness in v0.1.

## Raw row preservation at scale

Default is `raw_policy=full`. For huge rows, v0.2 may support external raw references.

Possible future design:

```text
raw/
  shard_0001.zstd.jsonl
  shard_0002.zstd.jsonl
```

AgentIR record stores:

```json
"raw": {
  "external_ref": {
    "uri": "raw/shard_0001.zstd.jsonl",
    "row_offset": 12345,
    "sha256": "..."
  }
}
```

v0.1 should keep raw rows directly unless explicitly overridden.

## Multiprocessing

Safe for JSONL when order preservation is optional or buffered.

Options:

```text
--jobs INT
--preserve-order / --no-preserve-order
--chunk-size INT
```

Rules:

- compiled DSL spec must be serializable or loaded once per worker;
- diagnostics must include original row index;
- output order should be preserved by default;
- failed rows should not kill the whole conversion unless `--strict` is set.

## Benchmark command

```bash
agentir dsl bench SPEC --input DATA --limit 100000 --batch-size 1024 --jobs 4
```

Report:

```text
Throughput
- records/sec
- MB/sec
- events/sec

Stage timings
- JSON decode
- detection
- variable binding
- tool registry extraction
- event emission
- Pydantic model creation
- output serialization

Top bottlenecks
- selectors
- transforms
- regex patterns
- JSON parsing fields
```

## Regression benchmarks

Add benchmark fixtures under:

```text
benchmarks/
  dsl/
    bench_sharegpt.py
    bench_openhands.py
    bench_hermes.py
```

Do not require benchmark tests in normal CI. Provide a manual command:

```bash
uv run pytest benchmarks/dsl --benchmark-only
```

If `pytest-benchmark` is not desired, implement simple timing scripts.

## Practical acceptance criteria

For v0.1 DSL runtime:

- can stream a JSONL file without loading it fully;
- handles at least 10k fixture-like rows in a single process without memory growth proportional to row count;
- `agentir dsl bench` reports per-stage timing;
- DSL output for five representative formats is semantically equivalent to hand-written frontends on fixtures;
- no conversion path uses arbitrary eval or external processes.

## Future optimization path

v0.2/v0.3:

- generated Python frontend;
- Arrow-native selectors for Parquet;
- DuckDB-based sampling/probing;
- optional Rust scanner for XML/tool blocks after profiling;
- compressed raw sidecar store;
- distributed conversion recipes for large HF datasets.
