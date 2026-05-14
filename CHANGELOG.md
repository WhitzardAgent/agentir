# Changelog

All notable changes to AgentIR will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2024-05-14

### Added

- Initial release of AgentIR, a compiler infrastructure for agentic trajectories.
- **DSL Runtime**: models, loader, and compiler (`RuntimeDSLFrontend`) for defining and compiling format DSL specifications.
- **5 built-in format DSL specs**: agenttrove, codex-swebenchpro, claude-code, openhands, hermes-agent.
- **8 CLI DSL subcommands**: `validate`, `probe`, `preview`, `convert`, `bench`, `diff`, `init`, `formats`.
- **12 passes**:
  - `parse-sharegpt`: parse conversations in ShareGPT format.
  - `parse-hermes-xml`: parse Hermes-style XML-wrapped tool calls.
  - `parse-openhands-tool-calls`: parse OpenHands tool-call structure.
  - `parse-claude-log`: parse Claude Code session logs.
  - `canonicalize-tools`: normalize tool definitions to a canonical form.
  - `pair-tool-results`: match tool calls with their corresponding results.
  - `normalize-outcome`: standardize outcome fields across formats.
  - `extract-patches`: extract code patches from tool results.
  - `redact-reasoning`: strip or redact reasoning content from messages.
  - `slice-training`: produce training-ready slices from compiled trajectories.
  - `verify`: validate trajectory structure and integrity.
- **Batch processing** with progress reporting and configurable parallelism.
- **Error quarantine**: isolate malformed records without aborting the entire batch.
- **Streaming converter**: process large datasets record-by-record with low memory overhead.
- **Pass manager**: supports pass groups, execution timing, and detailed run statistics.
- **174 tests** achieving 100% pass rate across the suite.
- Tested on 1.7M AgentTrove records (28M+ events) with 0 failures in controlled benchmark.
- Apache 2.0 license.
