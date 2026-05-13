# Roadmap

## v0.1: Compiler-shaped MVP

Goal: prove the architecture with five real trace families.

Deliverables:

1. Python package scaffold.
2. Pydantic AgentIR v0.1 models.
3. JSON Schema export.
4. Frontends:
   - AgentTrove
   - Codex SWE-bench Pro
   - Claude Code
   - OpenHands
   - Hermes Agent
5. Pass manager.
6. Passes:
   - parse-sharegpt
   - parse-hermes-xml
   - parse-claude-log
   - parse-openhands-tool-calls
   - canonicalize-tools
   - pair-tool-results
   - extract-patches
   - normalize-outcome
   - redact-reasoning
   - slice-training
   - verify
7. Backends:
   - sft
   - process-supervision
   - openai-tools
   - hermes-xml
   - openhands
   - sharegpt
8. CLI:
   - agentir-as
   - agentir-opt
   - agentir-llc
   - agentir verify
   - agentir schema export
   - agentir compile
9. Diagnostics and loss reports.
10. Fixtures and tests.
11. README and docs.

## v0.2: Better training views and observability

Add:

- Anthropic tools backend
- RL rollout backend
- DPO/preference backend
- OpenTelemetry backend
- OpenInference backend
- Artifact dependency analysis
- Trainability analysis
- trajectory quality scoring
- MkDocs documentation site
- GitHub Actions CI

## v0.3: Framework ecosystem

Add frontends/backends:

- LangGraph
- AutoGen
- CrewAI
- LlamaIndex agent traces
- MCP logs
- OpenAI Agents SDK tracing

Add:

- source-map inspection CLI
- interactive trace viewer prototype
- Airpack bundle format

## v0.4: Performance and scale

Add:

- DuckDB/Arrow batch processing
- optional Rust parser extension after profiling
- distributed conversion recipes
- dataset card generation
- large-scale conversion benchmarks

## Public positioning

Short tagline:

> AgentIR: a compiler infrastructure for agentic trajectories.

Long tagline:

> agentir parses heterogeneous agent traces into a canonical intermediate representation, runs verification and transformation passes, and lowers them into training, evaluation, replay, and framework-specific formats with explicit loss reports.

