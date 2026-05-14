#!/usr/bin/env python3
"""End-to-end AgentIR workflow example.

This script demonstrates the complete AgentIR pipeline:

1. Load (or define) a DSL format specification
2. Compile the DSL to a runtime frontend
3. Read source data from a JSONL file
4. Parse each source record into the AgentIR intermediate representation
5. Run the pass pipeline (normalization + verification) on each record
6. Print a summary of events per record and aggregate pipeline statistics

Usage:
    PYTHONPATH=src uv run python examples/end_to_end/workflow.py hilabihan
"""

from __future__ import annotations

import importlib
import os
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure src/ is on sys.path so that `import agentir` works.
# When the user runs with PYTHONPATH=src, this is already handled, but
# we add it explicitly as a fallback for direct invocation.
# ---------------------------------------------------------------------------
_project_root = Path(__file__).resolve().parent.parent.parent
_src_dir = _project_root / "src"
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

# ---------------------------------------------------------------------------
# Import pass modules so they self-register with the pass registry.
# This is the same pattern used by the CLI (see cli/main.py).
# ---------------------------------------------------------------------------
_pass_modules = [
    "agentir.passes.canonicalize_tools",
    "agentir.passes.extract_patches",
    "agentir.passes.normalize_outcome",
    "agentir.passes.pair_tool_results",
    "agentir.passes.parse_openhands_tool_calls",
    "agentir.passes.parse_sharegpt",
    "agentir.passes.redact_reasoning",
    "agentir.passes.slice_training",
    "agentir.passes.verify",
]
for mod_name in _pass_modules:
    try:
        importlib.import_module(mod_name)
    except Exception:
        pass  # Some passes may have optional dependencies

from agentir.dsl.loader import load_dsl
from agentir.dsl.compiler import compile_dsl_frontend
from agentir.frontends.base import FrontendContext
from agentir.io.jsonl import read_jsonl
from agentir.ir.record import AgentIRRecord
from agentir.passes.base import PassContext
from agentir.passes.manager import PassManager


# ==============================================================================
# Step 0: Define a minimal DSL specification suitable for sample_data.jsonl
# ==============================================================================

# We embed a minimal DSL definition as a YAML string.  This spec is
# purpose-built for our sample data format -- simple chat conversations
# with a "messages" array containing {role, content} objects (the
# standard ShareGPT-like schema).
#
# In real use you would load an existing spec from disk:
#
#     spec = load_dsl("dsl/formats/openhands.agentir.yaml")
#
# The embedded spec below covers:
#   - apiVersion & kind (required by the schema)
#   - metadata (human-readable name, title, version)
#   - source (where data comes from and how records are structured)
#   - detect rules (how to identify this data format among unknown sources)
#   - episodes/events (how to map source records to AgentIR events)
#   - passes (which passes to run by default)
# ------------------------------------------------------------------------------

_SHAREGPT_MINIMAL_DSL = """
apiVersion: agentir.qitor.ai/v0.1
kind: TrajectoryFormat
metadata:
  name: simple-chat
  title: Simple Chat Conversations
  version: "0.1.0"
  description: Minimal DSL for simple chat JSONL with messages array.
source:
  kind: jsonl
  record_mode: row
  framework: chat
  format: sharegpt
  raw_policy: full
detect:
  min_score: 0.50
  rules:
    - field_exists: "$.messages"
      score: 0.60
    - field_is_list: "$.messages"
      score: 0.40
episodes:
  - episode_id:
      template: "ep_{row_index}"
    events:
      - foreach:
          path: "$.messages[*]"
        as: turn
        index_as: i
        emit:
          event_id:
            template: "evt_{i:04d}"
          idx:
            var: i
          event_type:
            transform: role_to_event_type
            input:
              path: "turn.role"
          role:
            path: "turn.role"
          content:
            - type: text
              text:
                path: "turn.content"
          provenance:
            source_field:
              template: "messages[{i}]"
"""


# ==============================================================================
# Main workflow
# ==============================================================================

def main() -> None:
    """Run the end-to-end AgentIR workflow."""

    # ------------------------------------------------------------------
    # Step 1: Load the DSL format specification.  We write the embedded
    # YAML to a temporary file and use load_dsl(), which validates the
    # spec against the Pydantic schema.
    #
    # In a real pipeline you would point load_dsl() at a checked-in
    # *.agentir.yaml file in your project.
    # ------------------------------------------------------------------
    dsl_path = None
    try:
        # Write the embedded YAML to a temp file
        fd, dsl_path = tempfile.mkstemp(suffix=".agentir.yaml")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(_SHAREGPT_MINIMAL_DSL)

        print("Step 1: Loading DSL format specification...")
        spec = load_dsl(dsl_path)
        print(f"  Loaded format: {spec.metadata.name} v{spec.metadata.version}")
        print(f"  Description:   {spec.metadata.description}")
        print()

        # ------------------------------------------------------------------
        # Step 2: Compile the DSL spec into a RuntimeDSLFrontend.
        # This produces a callable frontend object that implements
        # BaseFrontend -- it can detect compatible samples and parse
        # them into AgentIRRecord instances.
        #
        # No code generation step is needed; the DSL is evaluated
        # at runtime against each input row.  The compiled frontend
        # is a lightweight object you can hold in memory or pickle.
        # ------------------------------------------------------------------
        print("Step 2: Compiling DSL to runtime frontend...")
        frontend = compile_dsl_frontend(spec, dsl_path)
        print(f"  Frontend name: {frontend.frontend_name}")
        print()

        # ------------------------------------------------------------------
        # Step 3: Read the sample data.  The read_jsonl() utility
        # returns an iterator of parsed dicts, one per JSON line.
        # ------------------------------------------------------------------
        data_path = Path(__file__).resolve().parent / "sample_data.jsonl"
        print(f"Step 3: Reading sample data from {data_path.name}...")
        raw_records = list(read_jsonl(data_path))
        print(f"  Found {len(raw_records)} source record(s)")
        print()

        # ------------------------------------------------------------------
        # Step 4: Parse each record into AgentIR format.
        # For each raw source row we create a FrontendContext (metadata
        # about the data origin) and call frontend.parse_record().
        #
        # The result is a list of AgentIRRecord objects -- the canonical
        # intermediate representation.  Each record contains episodes,
        # which contain events, content blocks, and provenance records.
        # ------------------------------------------------------------------
        print("Step 4: Parsing records into AgentIR format...")
        air_records: list[AgentIRRecord] = []
        for idx, raw in enumerate(raw_records):
            ctx = FrontendContext(
                dataset=None,    # Not loading from HF in this example
                config=None,
                split=None,
                row_index=idx,
            )
            result = frontend.parse_record(raw, ctx)
            if result.record is not None:
                air_records.append(result.record)
                event_count = sum(len(ep.events) for ep in result.record.episodes)
                print(f"  Record {result.record.record_id}: parsed -> {event_count} event(s)")
            else:
                print(f"  Record {idx}: WARNING -- parse produced no record")
        print(f"  Successfully parsed {len(air_records)}/{len(raw_records)} records")
        print()

        # ------------------------------------------------------------------
        # Step 5: Run the pass pipeline on each record.
        # The PassManager orchestrates a sequence of passes (each
        # implementing AgentIRPass) that transform and verify records.
        #
        # We use a well-known set of passes:
        #   parse-sharegpt       -- resolve ShareGPT-style content/roles
        #   canonicalize-tools   -- normalize tool-call formatting
        #   pair-tool-results    -- link tool calls to their results
        #   normalize-outcome    -- derive outcome status from data
        #   verify               -- structural integrity checks
        #
        # Each pass receives the output of the previous pass, so the
        # pipeline is compositional.
        # ------------------------------------------------------------------
        PASSES = [
            "parse-sharegpt",
            "canonicalize-tools",
            "pair-tool-results",
            "normalize-outcome",
            "verify",
        ]

        print(f"Step 5: Running pass pipeline: {' -> '.join(PASSES)}")
        manager = PassManager()
        pass_ctx = PassContext(strict=False)
        results = []
        for record in air_records:
            result = manager.run_pipeline(record, PASSES, pass_ctx)
            results.append(result)

            # Report events per record after pipeline
            total_events = sum(len(ep.events) for ep in result.record.episodes)
            diag_count = len(result.diagnostics)
            diag_status = ""
            if diag_count > 0:
                errors = sum(
                    1 for d in result.diagnostics
                    if d.severity.value in ("error", "fatal")
                )
                warnings = diag_count - errors
                diag_status = f" ({errors} error(s), {warnings} warning(s))"
            print(f"  {result.record.record_id}: {total_events} event(s){diag_status}")
        print()

        # ------------------------------------------------------------------
        # Step 6: Print aggregated pipeline summary.
        # The PassManager can produce aggregate statistics across all
        # results, including total events, elapsed time, diagnostics
        # by severity, and average metrics.
        # ------------------------------------------------------------------
        print("Step 6: Pipeline summary")
        print(manager.print_summary(results))

    finally:
        # Clean up the temporary DSL file
        if dsl_path and os.path.exists(dsl_path):
            os.unlink(dsl_path)


if __name__ == "__main__":
    main()
