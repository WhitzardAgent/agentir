from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from datasets import load_dataset


def load_hf_dataset(
    dataset_id: str,
    *,
    config: str | None = None,
    split: str = "train",
    streaming: bool = True,
    limit: int | None = None,
) -> Iterator[dict[str, Any]]:
    ds = load_dataset(dataset_id, name=config, split=split, streaming=streaming)
    count = 0
    for row in ds:
        yield dict(row)
        count += 1
        if limit is not None and count >= limit:
            break
