# -*- coding: utf-8 -*-
"""评估运行器:golden set → 检索/路由/引用指标 + 阈值建议(设计 §9.2)。"""
from __future__ import annotations

import json

from techdocs_rag.evaluation.metrics import (
    citation_accuracy,
    context_precision,
    context_recall,
    routing_accuracy,
    suggest_threshold,
)


class EvalRunner:
    def __init__(self, qa_service):
        self.qa = qa_service

    def run(self, golden_path: str) -> dict:
        entries = []
        with open(golden_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    entries.append(json.loads(line))
        per_query = []
        for entry in entries:
            expected = entry.get("expected_stack") or entry.get("expected_stacks") or []
            if isinstance(expected, str):
                expected = [expected]
            result = self.qa.ask(
                entry["query"],
                permissions=set(entry.get("permissions", ["public", "internal"])),
                version=entry.get("version"),
            )
            relevant = set(entry.get("relevant_source_ids", []))
            sources = result.context_source_ids
            per_query.append(
                {
                    "query": entry["query"],
                    "routing_ok": set(result.routing.get("stacks", [])) == set(expected),
                    "pred_stacks": result.routing.get("stacks"),
                    "expected_stacks": expected,
                    "context_recall": round(context_recall(sources, relevant), 4),
                    "context_precision": round(context_precision(sources, relevant), 4),
                    "citation_accuracy": round(citation_accuracy(result.citations), 4),
                    "refused": result.refused,
                    "expected_refusal": bool(entry.get("should_refuse", False)),
                    "has_relevant": bool(relevant),
                    "relevance": result.relevance,
                }
            )
        n = len(per_query)
        answered = [r for r in per_query if not r["refused"]]
        refused = [r for r in per_query if r["refused"]]
        routing_pairs = [
            (r["pred_stacks"], r["expected_stacks"]) for r in per_query if r["expected_stacks"]
        ]
        knowledge = [r for r in per_query if r["has_relevant"]]  # 拒答用例不进检索指标
        kmean = lambda key: (sum(r[key] for r in knowledge) / len(knowledge)) if knowledge else 0.0  # noqa: E731
        return {
            "n": n,
            "routing_accuracy": round(routing_accuracy(routing_pairs), 4),
            "context_recall": round(kmean("context_recall"), 4),
            "context_precision": round(kmean("context_precision"), 4),
            "citation_accuracy": round(kmean("citation_accuracy"), 4),
            "refusal_rate": round((len(refused) / n) if n else 0.0, 4),
            "refusal_correctness": round(
                (sum(1 for r in per_query if r["refused"] == r["expected_refusal"]) / n) if n else 0.0, 4
            ),
            "suggested_refusal_threshold": suggest_threshold(
                [r["relevance"] for r in answered], [r["relevance"] for r in refused]
            ),
            "per_query": per_query,
        }
