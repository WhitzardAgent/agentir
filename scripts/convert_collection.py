#!/usr/bin/env python3
"""Batch conversion script for AgentIR Collection.

Converts source datasets (AgentTrove, ClaudeCode) into 5 target formats:
  - OpenAI Chat Messages (openai-tools)
  - Anthropic Tools API (anthropic-tools)
  - OpenHands Native (openhands)
  - Hermes XML (hermes-xml)
  - AgentIR Canonical (agentir)

Usage:
    python scripts/convert_collection.py \
        --source agenttrove \
        --input data/agenttrove_sample.jsonl \
        --output-dir output/agenttrove \
        --formats all

    python scripts/convert_collection.py \
        --source claude-code \
        --input data/claude_code.jsonl \
        --output-dir output/claudecode \
        --formats openai-tools,anthropic-tools
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agentir.backends.base import BackendContext
from agentir.dsl.compiler import compile_dsl_frontend
from agentir.dsl.loader import load_dsl
from agentir.frontends.base import FrontendContext
from agentir.io.jsonl import read_jsonl, write_jsonl


ALL_FORMATS = ["openai-tools", "anthropic-tools", "openhands", "hermes-xml", "agentir"]

DSL_MAP = {
    "agenttrove": "dsl/formats/agenttrove.agentir.yaml",
    "claude-code": "dsl/formats/claude_code.agentir.yaml",
    "codex-swebenchpro": "dsl/formats/codex_swebenchpro.agentir.yaml",
    "hermes-agent": "dsl/formats/hermes_agent.agentir.yaml",
    "openhands": "dsl/formats/openhands.agentir.yaml",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AgentIR Collection batch converter")
    parser.add_argument(
        "--source",
        required=True,
        choices=list(DSL_MAP.keys()),
        help="Source dataset identifier",
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path to input JSONL file",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Output directory for converted files",
    )
    parser.add_argument(
        "--formats",
        default="all",
        help="Comma-separated target formats, or 'all'",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of records to process",
    )
    parser.add_argument(
        "--include-reasoning",
        action="store_true",
        help="Include reasoning events in output",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1024,
        help="Batch size for processing",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.formats == "all":
        target_formats = ALL_FORMATS
    else:
        target_formats = [f.strip() for f in args.formats.split(",")]
        unknown = set(target_formats) - set(ALL_FORMATS)
        if unknown:
            print(f"ERROR: Unknown format(s): {unknown}. Available: {ALL_FORMATS}")
            sys.exit(1)

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"ERROR: Input file not found: {input_path}")
        sys.exit(2)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    dsl_path = DSL_MAP[args.source]
    if not Path(dsl_path).exists():
        print(f"ERROR: DSL file not found: {dsl_path}")
        sys.exit(2)

    spec = load_dsl(dsl_path)
    frontend = compile_dsl_frontend(spec, dsl_path)

    import agentir.backends  # noqa: F401
    from agentir.backends.registry import get_backend
    from agentir.ir.record import AgentIRRecord

    print(f"Source: {args.source}")
    print(f"Input: {input_path}")
    print(f"Output: {output_dir}")
    print(f"Formats: {', '.join(target_formats)}")
    print()

    raw_records = list(read_jsonl(input_path, limit=args.limit))
    total = len(raw_records)
    print(f"Loaded {total} record(s)")

    # Phase 1: Convert to AgentIR Canonical
    print("\nPhase 1: Converting to AgentIR Canonical...")
    canonical_records: list[AgentIRRecord] = []
    failures = 0
    start = time.perf_counter()

    for i, rec in enumerate(raw_records):
        ctx = FrontendContext(
            dataset=spec.source.default_dataset,
            config=None,
            split=spec.source.default_split,
            row_index=i,
        )
        try:
            result = frontend.parse_record(rec, ctx)
            if result.record is not None:
                canonical_records.append(result.record)
            else:
                failures += 1
        except Exception as e:
            print(f"  ERROR row {i}: {e}")
            failures += 1

    elapsed = time.perf_counter() - start
    success = len(canonical_records)
    print(f"  Converted: {success}/{total} ({failures} failures)")
    print(f"  Rate: {success / elapsed:.1f} rec/s" if elapsed > 0 else "  Rate: N/A")

    # Save AgentIR Canonical if requested
    if "agentir" in target_formats:
        canonical_path = output_dir / "canonical.air.jsonl"
        count = write_jsonl(
            canonical_path,
            iter(r.model_dump(mode="json", exclude_none=True) for r in canonical_records),
        )
        print(f"  Wrote {count} records to {canonical_path}")

    # Phase 2: Lower to target formats
    lowering_formats = [f for f in target_formats if f != "agentir"]
    if lowering_formats:
        print(f"\nPhase 2: Lowering to {', '.join(lowering_formats)}...")

        for fmt in lowering_formats:
            print(f"\n  Lowering to {fmt}...")
            try:
                backend = get_backend(fmt)
            except KeyError as e:
                print(f"    SKIP: {e}")
                continue

            include_reasoning = args.include_reasoning or (fmt == "hermes-xml")
            ctx = BackendContext(
                reasoning_policy="preserve" if include_reasoning else "metadata_only",
                include_reasoning=include_reasoning,
                tool_policy="structured",
            )

            outputs: list[dict] = []
            total_losses = 0
            status_counts: dict[str, int] = {}
            fmt_start = time.perf_counter()

            for record in canonical_records:
                result = backend.lower_record(record, ctx)
                outputs.append(result.output)
                total_losses += len(result.report.losses)
                s = result.report.status.value
                status_counts[s] = status_counts.get(s, 0) + 1

            fmt_elapsed = time.perf_counter() - fmt_start

            out_path = output_dir / f"{fmt}.jsonl"
            count = write_jsonl(out_path, iter(outputs))

            print(f"    Wrote {count} records to {out_path}")
            print(f"    Time: {fmt_elapsed:.2f}s ({count / fmt_elapsed:.1f} rec/s)" if fmt_elapsed > 0 else "    Time: N/A")
            print(f"    Loss items: {total_losses}")
            for status, cnt in sorted(status_counts.items()):
                print(f"    {status}: {cnt}")

    print("\nDone.")


if __name__ == "__main__":
    main()
