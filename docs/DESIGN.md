# Design: AgentIR Compiler Infrastructure

## Mission

agentir makes heterogeneous agentic trajectories compilable.

It is inspired by LLVM/MLIR: source traces are parsed by frontends, normalized into an intermediate representation, transformed by pass pipelines, verified, and lowered into target formats with explicit diagnostics and loss reports.

## Conceptual mapping from LLVM

| LLVM concept | agentir equivalent |
|---|---|
| Source language | Agent framework trace / dataset format |
| Frontend | Dataset/framework adapter |
| LLVM IR | Canonical AgentIR |
| Module | `AgentIRModule` / dataset shard |
| Function | `Episode` / task run |
| Basic block | `Segment` / phase of a trajectory |
| Instruction | `Event` |
| Optimization pass | Analysis/transformation pass |
| Backend | Lowering target / exporter |
| Debug info | Source map / provenance |
| Verifier | AgentIR verifier |
| Diagnostic | Compiler-style error/warning/help |

## Multi-level IR

agentir uses multiple levels, not one flat schema.

```text
RawIR
  ↓ parser passes
ParsedIR
  ↓ canonicalization + recovery + verification
Canonical AgentIR
  ↓ projection/slicing/redaction
TrainingIR
  ↓ backend lowering
TargetIR
```

### RawIR

RawIR preserves original source records. It may contain incomplete, framework-specific, or unparsed fields.

Invariants:

- Never drop source fields.
- Preserve dataset name, config, split, row index, and source field paths.
- RawIR does not need to pass semantic verifier.

### ParsedIR

ParsedIR turns raw messages/logs/XML/tool-calls into typed events. It may contain low-confidence events.

Invariants:

- Every extracted event must contain provenance.
- Low-confidence inference must be marked with `confidence < 1.0`.
- Failed parse fragments must be preserved as `unparsed_fragment` events or raw attachments.

### Canonical AgentIR

Canonical AgentIR is the stable middle-end representation.

Invariants:

- Events have stable IDs and monotonically increasing `idx` inside an episode.
- Tool calls and tool results are paired when possible.
- Artifacts are referenced by ID, not duplicated in every event.
- Outcomes are normalized into a common status/reward/verifier model.
- Canonical AgentIR must pass the default verifier.

### TrainingIR

TrainingIR is a projection optimized for model training, not a canonical storage format.

Examples:

- SFT tool-use records
- Process supervision steps
- RL rollout tuples
- DPO preference pairs
- SWE patch training views

### TargetIR

TargetIR is a backend-specific output format such as OpenAI tools, Anthropic tools, Hermes XML, OpenHands trajectories, ShareGPT, OpenTelemetry, or OpenInference.

Backends must report losses.

## Dataflow

```text
agentir-as   source → RawIR/ParsedIR
agentir-opt  IR → IR through pass pipeline
agentir-llc  IR → target format
agentir      user-friendly umbrella command
```

## Frontend contract

A frontend must implement:

```python
class Frontend(Protocol):
    name: str
    source_kind: SourceKind

    def detect(self, sample: Mapping[str, Any]) -> float: ...
    def parse_record(self, record: Mapping[str, Any], context: FrontendContext) -> AgentIRRecord: ...
```

Requirements:

- Frontends must be lossless by default.
- Frontends must not perform expensive normalization that belongs in passes.
- Frontends must emit diagnostics instead of crashing on malformed records.
- Frontends must set `source.framework`, `source.dataset`, `source.format`, and `raw.record`.

## Pass contract

A pass must implement:

```python
class Pass(Protocol):
    name: str
    kind: PassKind  # parse | canonicalize | analysis | transform | verify | lowering_preparation

    def run(self, record: AgentIRRecord, ctx: PassContext) -> PassResult: ...
```

Passes must be composable. They must return:

- modified record or original record
- diagnostics
- optional analysis artifacts
- metrics

## Backend contract

A backend must implement:

```python
class Backend(Protocol):
    name: str
    target: str

    def lower_record(self, record: AgentIRRecord, ctx: BackendContext) -> LoweringResult: ...
```

Backends must always produce a `LossReport`:

```text
exact      no significant semantic loss
lossy      output is usable but some semantics are downgraded
partial    only core conversation/action/observation survived
unsupported target cannot represent this record
```

## Source maps

Every event must trace back to source.

```json
{
  "dataset": "lambda/hermes-agent-reasoning-traces",
  "config": "glm-5.1",
  "split": "train",
  "row_id": "123",
  "source_field": "conversations[4].value",
  "char_start": 120,
  "char_end": 560,
  "parser": "ParseHermesXMLPass",
  "confidence": 0.98
}
```

Source maps are mandatory for:

- parsed reasoning blocks
- parsed tool calls
- parsed tool results
- inferred terminal commands
- extracted patches
- recovered outcomes

## Reasoning policy

Reasoning is first-class but policy-controlled.

Supported policies:

| Policy | Behavior |
|---|---|
| `preserve` | Keep reasoning event content |
| `summarize` | Replace reasoning content with a summary placeholder or future model-generated summary |
| `drop` | Remove reasoning event from trainable projections |
| `redact` | Keep event metadata but redact content |
| `metadata_only` | Preserve only event existence and source span |

Default for public exports: `metadata_only` unless explicitly overridden.

## Naming

Use professional compiler terminology consistently:

- frontend, not importer
- backend/lowering, not exporter only
- pass, not processor
- verifier, not validator only
- diagnostic, not error message
- source map/provenance, not metadata only
- loss report, not warning log

