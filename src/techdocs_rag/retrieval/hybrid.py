# -*- coding: utf-8 -*-
"""混合检索:双通道召回 + RRF 融合 + authority 加权 + 归一化相关性信号(设计 §6.2/§6.4/§6.7)。"""
from __future__ import annotations

from techdocs_rag.models import AUTHORITY_WEIGHT, RetrievedChunk
from techdocs_rag.retrieval.filters import build_filter


def saturate(score: float) -> float:
    """BM25 分数饱和归一化到 (0,1),跨通道可比(设计 §6.7)。"""
    return score / (score + 8.0) if score > 0 else 0.0


def hybrid_search(store, collection, query_text, query_vec, filters, cfg, family_latest=None):
    """返回 (排序后的 RetrievedChunk 列表, relevance 信号)。

    relevance = max(向量通道 Top-1 cosine, saturate(BM25 通道 Top-1)),供拒答校准使用。
    """
    family_latest = family_latest or {}
    pred = build_filter(filters, family_latest)
    vhits = store.vector_search(collection, query_vec, cfg.vector_top_k, pred)
    bhits = store.bm25_search(collection, query_text, cfg.bm25_top_k, pred)

    rrf, vscores, bscores = {}, {}, {}
    for rank, (cid, s) in enumerate(vhits, 1):
        rrf[cid] = rrf.get(cid, 0.0) + 1.0 / (cfg.rrf_k + rank)
        vscores[cid] = max(vscores.get(cid, 0.0), s)
    for rank, (cid, s) in enumerate(bhits, 1):
        rrf[cid] = rrf.get(cid, 0.0) + 1.0 / (cfg.rrf_k + rank)
        bscores[cid] = max(bscores.get(cid, 0.0), s)

    chunks = store.get_chunks(collection, list(rrf))
    out = []
    for cid, fused in rrf.items():
        chunk = chunks.get(cid)
        if chunk is None:
            continue
        weight = AUTHORITY_WEIGHT.get(chunk.metadata.authority_level, 1.0)
        if chunk.metadata.deprecated:
            weight *= 0.8
        channels = (["vector"] if cid in vscores else []) + (["bm25"] if cid in bscores else [])
        out.append(
            RetrievedChunk(
                chunk=chunk,
                fused_score=fused * weight,
                vector_score=vscores.get(cid, 0.0),
                bm25_score=bscores.get(cid, 0.0),
                channels=channels,
            )
        )
    out.sort(key=lambda r: (-r.fused_score, r.chunk.id))

    relevance = 0.0
    if vscores:
        relevance = max(relevance, max(vscores.values()))
    if bscores:
        relevance = max(relevance, saturate(max(bscores.values())))
    return out, relevance
