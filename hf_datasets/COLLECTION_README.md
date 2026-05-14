# AgentIR Collection

A collection of agent trajectory datasets converted by [AgentIR](https://github.com/ravenSanstete/agentir) -- the LLVM for agent trajectories.

## What is AgentIR?

AgentIR is an open-source compiler infrastructure that turns heterogeneous agent traces into a canonical intermediate representation, then lowers them into training, evaluation, replay, and observability targets.

**Core thesis:** make agentic trajectories compilable -- the way LLVM made programs compilable.

## Collection Contents

| Source Dataset | Target Format | Dataset ID |
|---|---|---|
| AgentTrove | OpenAI Chat | `agentir/AgentTrove-OpenAI` |
| AgentTrove | Anthropic Tools | `agentir/AgentTrove-Anthropic` |
| AgentTrove | OpenHands | `agentir/AgentTrove-OpenHands` |
| AgentTrove | Hermes XML | `agentir/AgentTrove-Hermes` |
| AgentTrove | AgentIR Canonical | `agentir/AgentTrove-AgentIR` |
| Claude Code | OpenAI Chat | `agentir/ClaudeCode-OpenAI` |
| Claude Code | Anthropic Tools | `agentir/ClaudeCode-Anthropic` |
| Claude Code | OpenHands | `agentir/ClaudeCode-OpenHands` |
| Claude Code | Hermes XML | `agentir/ClaudeCode-Hermes` |
| Claude Code | AgentIR Canonical | `agentir/ClaudeCode-AgentIR` |

## Why Multiple Formats?

Different training frameworks require different data formats:
- **SFT trainers** (OpenAI, TRL) need `messages` with `tool_calls`
- **Anthropic fine-tuning** needs typed content blocks (`tool_use`, `tool_result`)
- **SWE-bench evaluators** need OpenHands trajectories with `model_patch`
- **Hermes/Reasoning models** need XML-tagged conversations
- **Research** needs the richest possible format (AgentIR Canonical)

## Quick Start

```python
from datasets import load_dataset

# Load AgentTrove in OpenAI format for SFT
ds = load_dataset("agentir/AgentTrove-OpenAI", split="train")

# Load AgentIR Canonical for maximum flexibility
ds = load_dataset("agentir/AgentTrove-AgentIR", split="train")
```

## Conversion Quality

| Metric | Value |
|---|---|
| Source records processed | 1,696,847 (AgentTrove full) |
| Source events processed | 28,206,633 |
| Throughput | 1,811 records/sec |
| Failures | 0 (100% success rate) |

## Links

- GitHub: https://github.com/ravenSanstete/agentir
- Documentation: https://github.com/ravenSanstete/agentir#readme
- CLI: `pip install agentir && agentir dsl convert`
