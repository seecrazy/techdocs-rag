# -*- coding: utf-8 -*-
"""评估指标与阈值建议器测试(设计 §9.1/§6.7)。"""
from __future__ import annotations

from techdocs_rag.evaluation.metrics import (
    citation_accuracy,
    context_precision,
    context_recall,
    routing_accuracy,
    suggest_threshold,
)
from techdocs_rag.models import Citation


class TestContextMetrics:
    def test_recall(self):
        assert context_recall(["x.md", "a.md", "y.md", "b.md"], {"a.md", "b.md", "c.md"}) == 2 / 3

    def test_recall_empty(self):
        assert context_recall([], {"a.md"}) == 0.0
        assert context_recall(["a.md"], set()) == 0.0

    def test_precision_ranking_aware(self):
        # 相关命中出现在 rank1(precision@1=1)与 rank3(precision@3=2/3),均值 (1+2/3)/2
        p = context_precision(["a.md", "x.md", "b.md"], {"a.md", "b.md"})
        assert abs(p - (1 + 2 / 3) / 2) < 1e-9

    def test_precision_no_hits(self):
        assert context_precision(["x.md", "y.md"], {"a.md"}) == 0.0


class TestRoutingAccuracy:
    def test_exact_set_match(self):
        pairs = [(["kafka"], "kafka"), (["spring", "k8s"], ["k8s", "spring"]), (["redis"], "kafka")]
        assert routing_accuracy(pairs) == 2 / 3

    def test_all_wrong(self):
        assert routing_accuracy([(["k8s"], "kafka")]) == 0.0


class TestCitationAccuracy:
    def test_mixed(self):
        cites = [Citation("a.md", "s", True), Citation("b.md", "s", True), Citation("g.md", "s", False)]
        assert citation_accuracy(cites) == 2 / 3

    def test_no_citations_counts_perfect(self):
        assert citation_accuracy([]) == 1.0


class TestSuggestThreshold:
    def test_separated(self):
        t = suggest_threshold([0.9, 0.8, 0.85, 0.95, 0.7], [0.1, 0.2, 0.05, 0.15, 0.25])
        assert 0.25 < t < 0.7

    def test_overlapping_still_returns_value(self):
        t = suggest_threshold([0.9, 0.8, 0.7, 0.6, 0.5], [0.1, 0.2, 0.3, 0.4, 0.5])
        assert 0.4 <= t <= 0.6

    def test_empty_inputs(self):
        assert suggest_threshold([], [0.1]) is None
        assert suggest_threshold([0.9], []) is None
