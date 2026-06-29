# -*- coding: utf-8 -*-
"""Per-rank JSONL logger for eval runs.

Each benchmark script imports this and emits one JSON line per processed
item, containing the model's raw output, the parsed click, the GT, and
correctness. Intended for post-hoc inspection of WHY the model got an
item right or wrong.

Usage pattern in a benchmark script:

    from eval_log import EvalLogger
    logger = EvalLogger(os.environ.get("LOG_DIR"), benchmark="screenspot", rank=rank)
    ...
    for result in batch_results:
        # (existing code that computes click_point, is_correct, etc.)
        logger.log({
            "task": task, "instruction": ..., "gt_bbox": ...,
            "raw_output": ..., "click_point": ..., "is_correct": ...,
        })
    ...
    logger.close()

Output: if LOG_DIR = /path/to/results/ and there are 8 ranks, writes
  /path/to/results/<benchmark>.rank0.jsonl ... <benchmark>.rank7.jsonl
You can merge with
  cat /path/to/results/screenspot.rank*.jsonl > screenspot.jsonl

If LOG_DIR env var is unset or empty, the logger becomes a no-op.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


class EvalLogger:
    def __init__(self, log_dir: str | None, benchmark: str, rank: int = 0) -> None:
        self.rank = int(rank)
        self.benchmark = benchmark
        self.enabled = bool(log_dir)
        self._fh = None
        self.path: Path | None = None
        if not self.enabled:
            return
        d = Path(log_dir)  # type: ignore[arg-type]
        d.mkdir(parents=True, exist_ok=True)
        shard = d / f"{benchmark}.rank{self.rank}.jsonl"
        # Truncate any previous shard so reruns don't append.
        self._fh = open(shard, "w", encoding="utf-8")
        self.path = shard

    def log(self, record: dict[str, Any]) -> None:
        if not self.enabled or self._fh is None:
            return
        try:
            self._fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        except Exception as exc:
            # Logger should never crash the eval run — print once and continue.
            print(f"[eval_log] failed to write record: {exc}")

    def close(self) -> None:
        if self._fh is not None:
            try:
                self._fh.flush()
                self._fh.close()
            except Exception:
                pass
            self._fh = None
