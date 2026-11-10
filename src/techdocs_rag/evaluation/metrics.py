# -*- coding: utf-8 -*-
"""评估指标与拒答阈值建议器(设计 §9.1、§6.7)。"""
from __future__ import annotations


def _percentile(values: list, q: float) -> float:
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round(q * (len(ordered) - 1)))))
    return ordered[idx]


def context_recall(retrieved: list, relevant: set) -> float:
    """召回率:相关来源被检索到的比例(漏召回=答错,首要指标)。"""
    rel = set(relevant)
    if not rel:
        return 0.0
    return len(rel & set(retrieved)) / len(rel)


def context_precision(retrieved: list, relevant: set) -> float:
    """排序感知精确率:按来源去重后,相关命中处的 precision@rank 均值(RAGAS 风格)。"""
    rel = set(relevant)
    if not rel or not retrieved:
        return 0.0
    unique = list(dict.fromkeys(retrieved))  # 同源多 chunk 只按首次出现计
    hits, contributions = 0, []
    for rank, sid in enumerate(unique, 1):
        if sid in rel:
            hits += 1
            contributions.append(hits / rank)
    return sum(contributions) / len(rel)


def routing_accuracy(pairs: list) -> float:
    """pairs: (预测栈列表, 期望栈 str 或列表);集合精确匹配。"""
    if not pairs:
        return 0.0
    ok = 0
    for predicted, expected in pairs:
        expected_set = {expected} if isinstance(expected, str) else set(expected or [])
        if set(predicted or []) == expected_set:
            ok += 1
    return ok / len(pairs)


def citation_accuracy(citations: list) -> float:
    """引用准确率:有效引用占比;无引用视为 1.0(无编造)。"""
    if not citations:
        return 1.0
    return sum(1 for c in citations if c.valid) / len(citations)


def suggest_threshold(relevant_scores: list, irrelevant_scores: list):
    """拒答阈值建议:相关问题 relevance p5 与无关问题 p95 的中点(设计 §6.7)。"""
    if not relevant_scores or not irrelevant_scores:
        return None
    low = _percentile(relevant_scores, 0.05)
    high = _percentile(irrelevant_scores, 0.95)
    return round((low + high) / 2.0, 4)
