# AgentIR Implementation Status

Generated: 2026-05-13
Based on: audit of src/, tests/, docs/, dsl/, schema/, prompts/

## Summary

81 tests pass, 13 fail (86% pass rate). Core IR models, frontends, passes, backends, and CLI infrastructure exist. DSL runtime (`*.agentir.yaml` loading/validation/compilation) is the major gap — documented in detail but not implemented.

## Current Capabilities

### IR Models (src/agentir/ir/)
- [x] AgentIRRecord with all fields per SPEC.md
- [x] IRLevel (raw/parsed/canonical/training/target)
- [x] Event with event_type, role, content blocks, action, observation, provenance, visibility
- [x] EventType, MessageRole, ContentType enums (all lowercase)
- [x] Action (ActionKind, tool_name, tool_call_id, arguments, call_style, side_effect_level)
- [x] Observation (ObservationKind, stdout, stderr, exit_code, error)
- [x] Outcome (OutcomeStatus, passed, verifier, reward, final_patch_artifact_id)
- [x] SourceRef, TaskSpec, ToolSpec, ActorSpec, Episode, Segment, Artifact
- [x] Provenance, Visibility (trainable, contains_reasoning, redaction_status)
- [x] Diagnostic with codes and severity
- [x] All values lowercase per SPEC.md
- [x] Pydantic v2 models with ConfigDict(extra="allow")

### Frontends (src/agentir/frontends/)
- [x] BaseFrontend + FrontendContext + FrontendResult
- [x] OpenHandsFrontend (`openhands`) — trajectories with tool_calls, model_patch
- [x] CodexSWEBenchProFrontend (`codex-swebenchpro`) — ShareGPT-style conversations
- [x] HermesAgentFrontend (`hermes-agent`) — ShareGPT + reasoning/tools
- [x] AgentTroveFrontend (`agenttrove`) — messages + reward
- [x] ClaudeCodeFrontend (`claude-code`) — messages_json, tools_json, gitdiff
- [x] Auto-detection via detect() with confidence scores
- [x] Frontend registry

### Passes (src/agentir/passes/)
- [x] PassManager — sequential pipeline execution
- [x] parse-hermes-xml — XML tool call/reasoning extraction
- [x] parse-openhands-tool-calls — OpenHands structured tool parsing
- [x] parse-sharegpt — ShareGPT role format parsing
- [x] parse-claude-log — Claude Code log parsing
- [x] pair-tool-results — match tool_calls with tool_results
- [x] canonicalize-tools — normalize tool specifications
- [x] normalize-outcome — outcome status normalization
- [x] extract-patches — git diff extraction
- [x] verify — verify record structure
- [x] redact-reasoning — reasoning content management
- [x] slice-training — training data slicing
- [x] Pass registry

### Backends (src/agentir/backends/)
- [x] Backend protocol + BackendContext
- [x] SFTBackend — supervised fine-tuning format
- [x] OpenAIToolsBackend — OpenAI function-calling format
- [x] HermesXMLBackend — Hermes XML format
- [x] OpenHandsBackend — OpenHands trajectory format
- [x] ShareGPTBackend — ShareGPT format
- [x] ProcessSupervisionBackend — step-level reward format
- [x] LossReporting — loss/lowering status tracking
- [x] Backend registry

### CLI (src/agentir/cli/)
- [x] agentir — main app (Typer)
- [x] agentir-as — frontend assembly (convert source to RawIR)
- [x] agentir-opt — pass optimization
- [x] agentir-llc — lowering/backend output
- [x] agentir schema export — JSON Schema generation
- [x] agentir verify — record verification
- [x] agentir compile — full pipeline

### Test Fixtures
- [x] tests/fixtures/hermes_agent_sample.jsonl
- [x] tests/fixtures/openhands_sample.jsonl
- [x] tests/fixtures/claude_code_sample.jsonl
- [x] tests/fixtures/agenttrove_sample.jsonl
- [x] tests/fixtures/codex_swebenchpro_sample.jsonl

### Tests
- [x] test_ir_models.py — IR model constructionInterval and validation
- [x] test_passes.py — pass execution tests
- [x] test_backends.py — backend lowering tests
- 81/94 tests passing (86%)

## Documented but NOT Yet Implemented

### P0: DSL Runtime
- [ ] `src/agentir/dsl/` package (models, loader, validator, compiler) — does not exist
- [ ] DSL schema models for TrajectoryFormat (apiVersion, kind, metadata, source, detect, vars, actors, tool_registry, task, episodes, outcome, passes, quality, performance)
- [ ] DSL validation against the YAML schema
- [ ] DSL compilation to runtime frontend
- [ ] RuntimeDSLFrontend class
- [ ] agentir-as --frontend-dsl flag

### P0: CLI DSL Commands
- [ ] agentir dsl validate `<dsl_file>`
- [ ] agentir dsl probe `<input_path>` 
- [ ] agentir dsl preview `<dsl_file>` `<input_path>` --limit N
- [ ] agentir dsl convert `<dsl_file>` `<input_path>` -o `<output_path>`
- [ ] agentir dsl bench `<dsl_file>` `<input_path>`
- [ ] agentir dsl diff `<dsl_file_a>` `<dsl_file_b>` `<input_path>`
- [ ] agentir dsl init --template
- [ ] agentir formats list
- [ ] agentir formats show `<name>`

### P Pran1: DSM L Format Equivalence
- [ ] Equivalence tests: DSL output == handwritten frontend output on same fixtures
- [ ] Five built-in DSL specs validating against real data

### P1: Performance
- [ ] Streaming JSONL reader (non-loading full dataset)
- [ ] Batch conversion with worker pool
- [ ] Fast path for common selectors
- [ ] Error quarantine / reject sink
- [ ] Benchmark CLI with records/sec, events/sec, memory metrics
- [ ] Stable progress display for large files

### P1: Terminal UI
- [ ] agentir dsl init interactive flow
- [ ] agentir dsl probe auto-analysis output
- [ ] agentir dsl preview rich mapping display
- [ ] Error highlighting for mapping failures

### P2: Developer Docs
- [ ] docs/DSL_QUICKSTART.md
- [ ] docs/ADDING_NEW_FORMAT_WITH_DSL.md
- [ ] docs/TERMINAL_UI.md
- [ ] docs/PERFORMANCE.md
- [ ] docs/ERRORS_AND_DIAGNOSTICS.md
- [ ] examples/custom_react_agent/
- [ ] examples/convert_existing_formats.sh
- [ ] examples/benchmark_large_jsonl.sh

## Current Test Failures (13 failing)

1. **test_backends.py** — `ObservationKind` not imported in helper functions (4 tests)
2. **test_backends.py** — `Obam0` typo in test_emits_trajectory_list (1 test)  
3. **test_ir_models.py** — JSON schema test asserts "raw" in flat (1 test)
4. **test_ir_models.py** — Extra fields not working due to ConfigDict mismatch (1 test)
5. **test_ir_models.py** — ContentBlock with JSON type not counted (1 test)
6. **test_passes.py** — `_make_event` missing `metadata` kwarg (1 test)
7. **test_passes.py** — ExtractPatches test expects artifacts on raw record (1 test)
8. **test_passes.py** — RedactReasoning tests (3 tests) — policy/implementation mismatch

## Technical Debt / Known Issuesinate

- Ruff reports ~87 style issues (long lines, SIM rules, etc.)
- Mypy not yet run
- No coverage measurement
- Some files have `from __future__ import annotations` inconsistently
- CLI commands partially wired but need DSL integration
- Pass manager exists but needs CLI flag integration for custom pass pipelines

## Round 1 Implementation Priorities

1. Fix 13 failing tests (quick wins)
2. Implement DSL models (src/agentir/dsl/models.py)
3. Implement DSL loader/validator (src/agentir/dsl/loader.py)
4. Implement DSL compiler/runtime frontend (src/agentir/dsl/compiler.py)
5. Add CLI dsl subcommands
6. Validate all 5 built-in DSL specs
7. Create fixture-based equivalence tests
8. Implement streaming reader and performance infrastructure
9. Write developer docs
10. Run full QA suite
