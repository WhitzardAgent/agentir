# End-to-End AgentIR Example

This directory contains a complete, self-contained example of the AgentIR workflow,
from loading a DSL format definition through the full pass pipeline.

## Files

- `sample_data.jsonl` -- Two simple chat conversations in JSONL format.
- `workflow.py` -- Runnable Python script that demonstrates the entire pipeline.

## Running the Example

```bash
# From the project root
PYTHONPATH=src uv run python examples/end_to_end/workflow.py
```

## What the Script Does

1. Loads a DSL format definition (uses `dsl/formats/openhands.agentir.yaml` as
   an example, but compiles it at runtime so it works with custom data too).
2. Compiles the DSL spec into a `RuntimeDSLFrontend` -- no codegen needed.
3. Reads `sample_data.jsonl` line-by-line.
4. Parses each source record into the AgentIR format (`AgentIRRecord`).
5. Runs the default pass pipeline (parse-sharegpt, canonicalize-tools,
   pair-tool-results, normalize-outcome, verify) on each record.
6. Prints a summary showing the number of events emitted per record and
   aggregated pipeline statistics.

## Key Concepts Illustrated

- **DSL compilation**: `load_dsl()` + `compile_dsl_frontend()` turn a YAML spec
  into a ready-to-use parser.
- **Frontend parsing**: `frontend.parse_record()` maps raw data to
  `AgentIRRecord` IR nodes.
- **Pass pipeline**: `PassManager.run_pipeline()` applies a sequence of
  normalization and verification passes.
- **Provenance tracking**: Every event carries a `Provenance` record showing
  its origin in the source data.
