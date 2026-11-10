# -*- coding: utf-8 -*-
"""全链路 Trace(JSONL)与用户反馈回流(设计 §9.3)。"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone


class TraceStore:
    def __init__(self, dirpath):
        self.dir = str(dirpath)
        os.makedirs(self.dir, exist_ok=True)
        self.trace_file = os.path.join(self.dir, "trace.jsonl")
        self.feedback_file = os.path.join(self.dir, "feedback.jsonl")

    def append(self, record: dict) -> None:
        record.setdefault("ts", datetime.now(timezone.utc).isoformat())
        with open(self.trace_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def record_feedback(self, trace_id: str, helpful: bool, comment: str = "") -> None:
        with open(self.feedback_file, "a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "trace_id": trace_id,
                        "helpful": helpful,
                        "comment": comment,
                        "ts": datetime.now(timezone.utc).isoformat(),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    def read_traces(self, limit: int = 100) -> list:
        if not os.path.exists(self.trace_file):
            return []
        with open(self.trace_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
        out = []
        for line in lines[-limit:]:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out
