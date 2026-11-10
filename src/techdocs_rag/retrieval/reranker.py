# -*- coding: utf-8 -*-
"""两阶段重排:Noop / LLM pointwise / Cross-Encoder(惰性)(设计 §6.6)。"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod

_SCORE_LINE = re.compile(r"([A-Z])\s*[:：]\s*(\d+(?:\.\d+)?)")


class Reranker(ABC):
    @abstractmethod
    def rerank(self, query: str, candidates: list) -> list:
        raise NotImplementedError


class NoopReranker(Reranker):
    """开发默认:沿用 RRF×authority 融合序。"""

    def rerank(self, query: str, candidates: list) -> list:
        out = list(candidates)
        for r in out:
            r.rerank_score = r.fused_score
        return out


class LLMReranker(Reranker):
    """LLM pointwise 打分(0-10);解析失败回退原序。"""

    def __init__(self, llm, max_candidates: int = 20, max_chars: int = 300):
        self.llm = llm
        self.max_candidates = max_candidates
        self.max_chars = max_chars

    def rerank(self, query: str, candidates: list) -> list:
        out = list(candidates)
        if not out:
            return out
        pool = out[: self.max_candidates]
        labels = [chr(ord("A") + i) for i in range(len(pool))]
        lines = "\n".join(
            "片段%s: %s" % (label, r.chunk.text[: self.max_chars].replace("\n", " "))
            for label, r in zip(labels, pool)
        )
        system = (
            "你是相关性评审。对每个片段与查询的相关性打 0-10 分,"
            "每行一个,格式如 A: 8。只输出打分行。"
        )
        try:
            raw = self.llm.chat(system, [{"role": "user", "content": "查询: %s\n\n%s" % (query, lines)}])
        except Exception:  # noqa: BLE001
            raw = ""
        scores = {m.group(1): float(m.group(2)) / 10.0 for m in _SCORE_LINE.finditer(raw)}
        scored, unscored = [], []
        for label, r in zip(labels, pool):
            if label in scores:
                r.rerank_score = scores[label]
                scored.append(r)
            else:
                unscored.append(r)
        scored.sort(key=lambda r: -r.rerank_score)
        return scored + unscored + out[len(pool) :]


class CrossEncoderReranker(Reranker):
    """bge-reranker-v2-m3(中英混合);需要 pip install sentence-transformers。"""

    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3"):
        self.model_name = model_name
        self._model = None

    def _load(self):
        if self._model is None:
            from sentence_transformers import CrossEncoder  # 惰性导入

            self._model = CrossEncoder(self.model_name, max_length=512)
        return self._model

    def rerank(self, query: str, candidates: list) -> list:
        out = list(candidates)
        if not out:
            return out
        model = self._load()
        pairs = [(query, r.chunk.text[:1024]) for r in out]
        probs = model.predict(pairs)
        for r, p in zip(out, probs):
            r.rerank_score = float(p)
        out.sort(key=lambda r: -r.rerank_score)
        return out
