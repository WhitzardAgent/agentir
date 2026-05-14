# AgentIR

[![Version](https://img.shields.io/badge/version-0.1.0-blue)](https://github.com/ravenSanstete/agentir)
[![Python](https://img.shields.io/badge/python-%3E%3D3.11-3776AB?logo=python&logoColor=ffd343)](https://github.com/ravenSanstete/agentir)
[![License](https://img.shields.io/badge/license-Apache--2.0-brightgreen)](https://github.com/ravenSanstete/agentir/blob/main/LICENSE)
[![Tests](https://img.shields.io/badge/tests-174%20passed-success)](https://github.com/ravenSanstete/agentir)
[![Code style](https://img.shields.io/badge/code%20style-ruff%20%2B%20mypy-7B61FF)](https://github.com/ravenSanstete/agentir)
[![Status](https://img.shields.io/badge/status-alpha-orange)](https://github.com/ravenSanstete/agentir)

**A compiler infrastructure for agentic trajectories.**

AgentIR turns heterogeneous traces from agent frameworks, coding assistants, GUI/browser agents, tool-use agents, evaluation sandboxes, and research datasets into a canonical intermediate representation that can be verified, transformed, analyzed, and lowered into training, evaluation, replay, and observability targets.

> Core thesis: **make agentic trajectories compilable** -- the way LLVM made programs compilable and MLIR made machine-learning graphs compilable.

---

## Architecture

```
Source Traces
  AgentTrove / Codex SWE-bench / Claude Code / OpenHands / Hermes /
  LangGraph / AutoGen / MCP logs / custom JSONL / custom Parquet
       |
Frontends
  Python frontends or user-defined *.agentir.yaml DSL frontends
       |
RawIR  -->  ParsedIR  -->  Canonical AgentIR
       |
Pass Pipeline
  parse -> canonicalize -> pair -> redact -> slice -> verify -> ...
       |
Backends (lowering targets)
  SFT / RL / DPO / tool-use / observability / replay / framework-native
```

---

## Key Features

- **Compiler-style architecture** -- frontends, multi-level IR, pass manager, backends, and diagnostics, modeled after LLVM/MLIR
- **5 built-in format frontends** -- AgentTrove, Codex SWE-bench Pro, Claude Code, OpenHands, Hermes Agent
- **User-extensible DSL** -- define new trajectory formats declaratively with `*.agentir.yaml` files; no Python required
- **8 CLI subcommands** -- `dsl validate`, `probe`, `preview`, `convert`, `bench`, `diff`, `init`, `formats`
- **174 tests with 100% pass rate** and **~12K lines of Python**
- **Battle-tested at scale** -- 1.7M AgentTrove records (28M+ events) processed with **0 failures**
- **Streaming JSONL**, batched processing, error quarantine, and compiled selectors
- **Pass-based processing** -- parse, canonicalize, pair, redact, slice, and verify are separate, composable passes
- **Compiler-style diagnostics** -- diagnostic codes, severity levels, source references, and suggested fixes
- **Event-graph model** -- events carry `action`, `observation`, `artifact`, `state`, `control`, and `provenance`
- **Loss-aware backend lowering** -- every backend emits an explicit loss report detailing what was preserved, degraded, or dropped

---

## Installation

```bash
git clone https://github.com/ravenSanstete/agentir.git
cd agentir

# using uv (recommended)
uv sync

# or standard pip
pip install -e .
```

**Requirements:** Python >= 3.11

---

## Quickstart

The following 6 steps take you from raw heterogeneous traces to verified, canonical AgentIR in under 5 minutes.

```bash
# 1. Validate a DSL format specification
agentir dsl validate dsl/formats/agenttrove.agentir.yaml

# 2. Probe your data to see its structure
agentir dsl probe --input data/my_data.jsonl --dsl dsl/formats/agenttrove.agentir.yaml

# 3. Preview the first 3 converted records
agentir dsl preview --dsl dsl/formats/agenttrove.agentir.yaml \
  --input data/my_data.jsonl --limit 3

# 4. Convert to AgentIR format
agentir dsl convert --dsl dsl/formats/agenttrove.agentir.yaml \
  --input data/my_data.jsonl --output out.air.jsonl

# 5. Run the pass pipeline end-to-end
agentir compile --frontend agenttrove --input data/my_data.jsonl \
  --passes parse-sharegpt,canonicalize-tools,pair-tool-results,normalize-outcome,verify \
  --output out.canonical.air.jsonl

# 6. Benchmark throughput on 10K records
agentir dsl bench dsl/formats/agenttrove.agentir.yaml \
  --input data/my_data.jsonl --limit 10000
```

---

## Core Concepts

| Concept | Description |
|---|---|
| **AgentIR Record** | Top-level container: one row of source data plus its canonical AgentIR representation |
| **Episode** | A sequence of events that forms a complete agent interaction session |
| **Event** | The fundamental unit: an `action`, `observation`, `artifact`, `state`, `control`, or `outcome` step with provenance |
| **Pass** | A single, named transformation that operates on AgentIR records (parse, canonicalize, pair, verify, etc.) |
| **Frontend** | Parses one specific trajectory format and emits `RawIR` records |
| **DSL** | Declarative YAML-based format definition language (`*.agentir.yaml`) for user-defined frontends |
| **Backend** | Lowers canonical AgentIR into a target format (SFT training, RL replay, observability span, etc.) |
| **IR Levels** | `RawIR` (source-preserving) -> `ParsedIR` (structured) -> `Canonical AgentIR` (pass-applied, verified) |

---

## Project Structure

```
src/agentir/
  ir/              AgentIR schema models (event, action, observation, record)
  dsl/             DSL models, loader, compiler (YAML -> runtime frontend)
  frontends/       Base frontend + 5 built-in format frontends
  passes/          Pass base, registry, manager, and 12 pass implementations
  backends/        Training, evaluation, and observability backends
  cli/             Typer CLI main entry with subcommands
  io/              Streaming JSONL, Parquet, batched processing
  diagnostics/     Diagnostic model and reporter

dsl/formats/       5 built-in *.agentir.yaml DSL format specifications
tests/             174 tests (pytest)
examples/          End-to-end workflow examples
docs/              Architecture, SPEC, DSL, and developer documentation
```

---

## Performance

Verified on the full **1.7M-record AgentTrove dataset** (28M+ events):

| Metric | Value |
|---|---|
| Records processed | 1,711,738 |
| Events processed | 28,206,633 |
| Throughput (records/sec) | 1,811 |
| Throughput (events/sec) | 30,136 |
| Failures | 0 |

---

## HuggingFace Datasets

Auto-converted trajectory datasets are available on HuggingFace under the [WhitzardAgent](https://huggingface.co/WhitzardAgent) organization as part of the [AgentIR Collection](https://huggingface.co/collections/WhitzardAgent/agentir-collection-6a05bbc07ccbd6e92acd596a):

| Dataset | Format | Records |
|---|---|---|
| [AgentTrove-AgentIR](https://huggingface.co/datasets/WhitzardAgent/AgentTrove-AgentIR) | AgentIR Canonical | 50,000 |
| [AgentTrove-OpenAI](https://huggingface.co/datasets/WhitzardAgent/AgentTrove-OpenAI) | OpenAI Chat Messages | 50,000 |
| [AgentTrove-Anthropic](https://huggingface.co/datasets/WhitzardAgent/AgentTrove-Anthropic) | Anthropic Tools API | 50,000 |
| [AgentTrove-OpenHands](https://huggingface.co/datasets/WhitzardAgent/AgentTrove-OpenHands) | OpenHands Trajectory | 50,000 |
| [AgentTrove-Hermes](https://huggingface.co/datasets/WhitzardAgent/AgentTrove-Hermes) | Hermes XML | 50,000 |
| [ClaudeCode-AgentIR](https://huggingface.co/datasets/WhitzardAgent/ClaudeCode-AgentIR) | AgentIR Canonical | 32,133 |
| [ClaudeCode-OpenAI](https://huggingface.co/datasets/WhitzardAgent/ClaudeCode-OpenAI) | OpenAI Chat Messages | 32,133 |
| [ClaudeCode-Anthropic](https://huggingface.co/datasets/WhitzardAgent/ClaudeCode-Anthropic) | Anthropic Tools API | 32,133 |
| [ClaudeCode-OpenHands](https://huggingface.co/datasets/WhitzardAgent/ClaudeCode-OpenHands) | OpenHands Trajectory | 32,133 |
| [ClaudeCode-Hermes](https://huggingface.co/datasets/WhitzardAgent/ClaudeCode-Hermes) | Hermes XML | 32,133 |

```python
from datasets import load_dataset

# Load in your preferred format
ds = load_dataset("WhitzardAgent/AgentTrove-OpenAI", split="train")
```

All datasets were auto-converted by AgentIR with 100% success rate (0 failures).
AgentTrove: 50,000 records at 1,281 rec/sec. ClaudeCode: 32,133 records at 317 rec/sec (full dataset, 100% parse rate).

---

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on development setup, coding standards, testing requirements, and the pull-request process.

All contributions must pass the existing test suite (`174 tests`, 100% pass rate) and conform to `ruff` + `mypy` style rules.

---

## License

This project is licensed under the Apache License 2.0. See [LICENSE](LICENSE) for the full text.

---

## Acknowledgments

AgentIR draws inspiration from and builds upon:

- **LLVM / MLIR** -- compiler infrastructure design, multi-level IR, and pass-manager architecture
- **Hugging Face Datasets** -- data loading patterns and Parquet/Arrow ecosystem
- **AgentTrove** (`open-thoughts/AgentTrove`) -- ShareGPT-style agent traces at scale
- **Codex SWE-bench Pro** (`Inferact/codex_swebenchpro_traces`) -- coding-agent trajectories
- **Claude Code** (`nlile/misc-merged-claude-code-traces-v1`) -- tool-use and multi-turn traces
- **OpenHands** (`nvidia/SWE-Hero-openhands-trajectories`) -- structured trajectory format
- **Hermes Agent** (`lambda/hermes-agent-reasoning-traces`) -- XML-based tool-call traces
