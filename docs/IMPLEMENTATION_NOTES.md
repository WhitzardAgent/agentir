# Implementation Notes for Maintainers

## Why Python is acceptable

Python is not only acceptable; it is the right v0.1 choice. The first users will be ML researchers and agent-framework developers working with Hugging Face datasets, JSONL, Parquet, Pydantic-compatible schemas, and Python training pipelines.

A future high-performance Rust layer can be added after the IR and pass architecture stabilize. Do not prematurely optimize.

## What makes this project globally competitive

1. Clear compiler metaphor.
2. Real frontends for real trace datasets, not toy examples.
3. Loss-aware lowering.
4. Source maps and diagnostics.
5. Training-first projections.
6. Strong docs and CLI.
7. Stable schema with extension dialects.

## Early public demo script

```bash
# 1. Parse Hermes fixture
agentir-as --frontend hermes-agent --input tests/fixtures/hermes_agent_sample.jsonl --output demo/hermes.raw.air.jsonl

# 2. Canonicalize and verify
agentir-opt demo/hermes.raw.air.jsonl \
  --passes parse-hermes-xml,canonicalize-tools,pair-tool-results,normalize-outcome,verify \
  --output demo/hermes.canonical.air.jsonl \
  --report demo/hermes.verify.md

# 3. Lower to SFT
agentir-llc demo/hermes.canonical.air.jsonl \
  --target sft \
  --output demo/hermes.sft.jsonl \
  --loss-report demo/hermes.sft.loss.md

# 4. Lower to OpenAI tool format
agentir-llc demo/hermes.canonical.air.jsonl \
  --target openai-tools \
  --output demo/hermes.openai_tools.jsonl \
  --loss-report demo/hermes.openai_tools.loss.md
```

