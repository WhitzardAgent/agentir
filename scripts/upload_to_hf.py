#!/usr/bin/env python3
"""Upload converted datasets to HuggingFace Hub.

Uploads each dataset from the local output directory to the HuggingFace Hub
under the `agentir` organization (or a specified namespace).

Prerequisites:
    pip install huggingface_hub
    huggingface-cli login

Usage:
    # Upload all datasets
    python scripts/upload_to_hf.py --namespace agentir --input-dir output/

    # Upload a single dataset
    python scripts/upload_to_hf.py --namespace agentir --input-dir output/ --dataset AgentTrove-OpenAI

    # Dry run (show what would be uploaded)
    python scripts/upload_to_hf.py --namespace agentir --input-dir output/ --dry-run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


DATASETS = [
    "AgentTrove-OpenAI",
    "AgentTrove-Anthropic",
    "AgentTrove-OpenHands",
    "AgentTrove-Hermes",
    "AgentTrove-AgentIR",
    "ClaudeCode-OpenAI",
    "ClaudeCode-Anthropic",
    "ClaudeCode-OpenHands",
    "ClaudeCode-Hermes",
    "ClaudeCode-AgentIR",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Upload AgentIR Collection datasets to HuggingFace")
    parser.add_argument(
        "--namespace",
        default="agentir",
        help="HuggingFace organization or user namespace (default: agentir)",
    )
    parser.add_argument(
        "--input-dir",
        default="output",
        help="Base directory containing converted dataset files",
    )
    parser.add_argument(
        "--readme-dir",
        default="hf_datasets",
        help="Directory containing dataset README.md files",
    )
    parser.add_argument(
        "--dataset",
        default=None,
        help="Upload a single dataset instead of all",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be uploaded without actually uploading",
    )
    parser.add_argument(
        "--private",
        action="store_true",
        help="Make datasets private",
    )
    return parser.parse_args()


def upload_dataset(
    dataset_name: str,
    namespace: str,
    input_dir: Path,
    readme_dir: Path,
    dry_run: bool,
    private: bool,
) -> bool:
    repo_id = f"{namespace}/{dataset_name}"

    readme_path = readme_dir / dataset_name / "README.md"
    if not readme_path.exists():
        print(f"  WARNING: README not found at {readme_path}")
        return False

    data_file = input_dir / dataset_name / "data.jsonl"
    if not data_file.exists():
        alt_paths = [
            input_dir / f"{dataset_name.lower()}.jsonl",
            input_dir / dataset_name / "canonical.air.jsonl",
        ]
        for alt in alt_paths:
            if alt.exists():
                data_file = alt
                break
        else:
            print(f"  WARNING: Data file not found for {dataset_name}")
            print(f"  Expected: {data_file}")
            return False

    if dry_run:
        print(f"  [DRY RUN] Would upload:")
        print(f"    README: {readme_path}")
        print(f"    Data:   {data_file}")
        print(f"    Repo:   {repo_id}")
        print(f"    Private: {private}")
        return True

    try:
        from huggingface_hub import HfApi
    except ImportError:
        print("ERROR: huggingface_hub is not installed. Run: pip install huggingface_hub")
        sys.exit(1)

    api = HfApi()

    try:
        api.create_repo(
            repo_id=repo_id,
            repo_type="dataset",
            private=private,
            exist_ok=True,
        )
        print(f"  Created/verified repo: {repo_id}")
    except Exception as e:
        print(f"  ERROR creating repo: {e}")
        return False

    try:
        api.upload_file(
            path_or_fileobj=str(readme_path),
            path_in_repo="README.md",
            repo_id=repo_id,
            repo_type="dataset",
        )
        print(f"  Uploaded README.md")

        api.upload_file(
            path_or_fileobj=str(data_file),
            path_in_repo="data.jsonl",
            repo_id=repo_id,
            repo_type="dataset",
        )
        print(f"  Uploaded data.jsonl")

    except Exception as e:
        print(f"  ERROR uploading files: {e}")
        return False

    print(f"  SUCCESS: {repo_id}")
    return True


def create_collection(
    namespace: str,
    dry_run: bool,
) -> None:
    if dry_run:
        print(f"\n[DRY RUN] Would create collection: {namespace}/agentir-collection")
        return

    try:
        from huggingface_hub import HfApi
    except ImportError:
        return

    api = HfApi()

    try:
        collection = api.create_collection(
            collection_name="AgentIR Collection",
            namespace=namespace,
            description="Agent trajectory datasets converted by AgentIR -- the LLVM for agent trajectories.",
        )
        print(f"\nCreated collection: {collection.slug}")

        for ds in DATASETS:
            try:
                api.add_item_to_collection(
                    collection_slug=collection.slug,
                    item_id=f"{namespace}/{ds}",
                    item_type="dataset",
                )
                print(f"  Added {namespace}/{ds}")
            except Exception as e:
                print(f"  WARNING: Could not add {ds}: {e}")

    except Exception as e:
        print(f"\nWARNING: Could not create collection: {e}")
        print("You can create it manually at https://huggingface.co/collections")


def main() -> None:
    args = parse_args()

    input_dir = Path(args.input_dir)
    readme_dir = Path(args.readme_dir)

    datasets = [args.dataset] if args.dataset else DATASETS

    if args.dataset and args.dataset not in DATASETS:
        print(f"ERROR: Unknown dataset '{args.dataset}'. Available: {', '.join(DATASETS)}")
        sys.exit(1)

    print(f"Namespace: {args.namespace}")
    print(f"Input dir: {input_dir}")
    print(f"README dir: {readme_dir}")
    print(f"Datasets: {len(datasets)}")
    print()

    success_count = 0
    fail_count = 0

    for ds in datasets:
        print(f"Processing: {ds}")
        ok = upload_dataset(
            dataset_name=ds,
            namespace=args.namespace,
            input_dir=input_dir,
            readme_dir=readme_dir,
            dry_run=args.dry_run,
            private=args.private,
        )
        if ok:
            success_count += 1
        else:
            fail_count += 1
        print()

    print(f"Results: {success_count} succeeded, {fail_count} failed")

    if not args.dataset:
        print("\nCreating collection...")
        create_collection(args.namespace, args.dry_run)


if __name__ == "__main__":
    main()
