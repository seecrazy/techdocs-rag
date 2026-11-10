# -*- coding: utf-8 -*-
"""混合检索测试:RRF×authority 次序 / 权限谓词 / latest 与显式版本 / 重排 / 相关性信号(设计 §6)。"""
from __future__ import annotations

import pytest

from techdocs_rag.config import RetrievalConfig
from techdocs_rag.embeddings import HashEmbedder
from techdocs_rag.models import Chunk, ChunkMetadata, RetrievedChunk
from techdocs_rag.retrieval.filters import RetrievalFilters, build_filter
from techdocs_rag.retrieval.hybrid import hybrid_search, saturate
from techdocs_rag.retrieval.reranker import LLMReranker, NoopReranker
from techdocs_rag.storage.chunkstore import SQLiteChunkStore
from techdocs_rag.storage.indexstore import IndexStore


def make_chunk(cid, text, source_id, **meta):
    base = dict(
        source_id=source_id,
        source_type="local_file",
        tech_stack="kafka",
        doc_type="guide",
        authority_level="authoritative",
        version="3.6",
        family_key="kafka/guide.md",
        section="s",
    )
    base.update(meta)
    return Chunk(cid, text, ChunkMetadata.from_dict(base))


@pytest.fixture()
def store(tmp_path):
    s = IndexStore(SQLiteChunkStore(tmp_path / "c.db"))
    embedder = HashEmbedder()
    chunks = [
        make_chunk("A", "session.timeout.ms 默认 45000,重平衡触发条件说明", "kafka/guide.md",
                   authority_level="authoritative", permission_scope="public"),
        make_chunk("B", "工单:session.timeout.ms 调大到 60000 后重平衡消失", "tickets/t1.md",
                   authority_level="operational", permission_scope="internal", version="unknown",
                   family_key="tickets/t1.md", doc_type="troubleshooting"),
        make_chunk("C", "博客:session.timeout.ms 与心跳的最佳实践分享", "web/blog.md",
                   authority_level="external", permission_scope="public", version="unknown",
                   family_key="web/blog.md"),
        make_chunk("D", "旧版重平衡说明:session.timeout.ms 旧语义", "kafka/v1.0/guide.md",
                   permission_scope="public", version="1.0", superseded=True),
    ]
    for c in chunks:
        c.embedding = embedder.embed_texts([c.text])[0]
    s.upsert_chunks("collection_kafka", chunks)
    return s


CFG = RetrievalConfig()
EMB = HashEmbedder()
FAMILY_LATEST = {"kafka/guide.md": "3.6"}


def _search(store, query, filters):
    vec = EMB.embed_texts([query])[0]
    return hybrid_search(store, "collection_kafka", query, vec, filters, CFG, family_latest=FAMILY_LATEST)


class TestSaturate:
    def test_monotonic_and_bounded(self):
        assert saturate(0) == 0
        assert 0 < saturate(4) < saturate(16) < saturate(64) < 1


class TestHybridOrder:
    def test_authority_weighting_order(self, store):
        results, _rel = _search(store, "session.timeout.ms 重平衡", RetrievalFilters(permissions={"public", "internal"}))
        sources = [r.chunk.id for r in results[:3]]
        assert sources == ["A", "B", "C"], "authoritative > operational > external(设计 §6.4)"

    def test_deprecated_downweighted(self, store):
        # 同文本孪生块:原始 RRF 相同,仅 deprecated 不同,次序只能由 ×0.8 决定
        chunk = store.get_chunks("collection_kafka", ["A"])["A"]
        twin = make_chunk(
            "A2", chunk.text, "kafka/guide2.md",
            authority_level="authoritative", permission_scope="public",
            deprecated=True, family_key="kafka/guide2.md",
        )
        twin.embedding = chunk.embedding
        store.upsert_chunks("collection_kafka", [twin])
        results, _ = _search(store, "session.timeout.ms 重平衡", RetrievalFilters(permissions={"public"}))
        ids = [r.chunk.id for r in results]
        assert ids.index("A") < ids.index("A2"), "deprecated 标记应触发 ×0.8 降权(设计 §6.4)"


class TestFilters:
    def test_permission_at_channel_level(self, store):
        results, _ = _search(store, "session.timeout.ms", RetrievalFilters(permissions={"internal"}))
        assert results and all(r.chunk.id == "B" for r in results), "权限过滤在通道内完成,B(operational)胜出"

    def test_default_latest_excludes_superseded(self, store):
        results, _ = _search(store, "session.timeout.ms 重平衡", RetrievalFilters(permissions={"public", "internal"}))
        ids = [r.chunk.id for r in results]
        assert "D" not in ids, "默认 latest:superseded 旧版本被过滤(设计 §6.5)"

    def test_explicit_version_penetrates(self, store):
        results, _ = _search(store, "旧版 session.timeout.ms", RetrievalFilters(permissions={"public", "internal"}, version="1.0"))
        ids = [r.chunk.id for r in results]
        assert "D" in ids, "显式版本可穿透 superseded"
        assert "A" not in ids, "版本 3.6 不匹配显式 1.0"


class TestRelevance:
    def test_channels_populated(self, store):
        results, rel = _search(store, "session.timeout.ms 重平衡", RetrievalFilters(permissions={"public", "internal"}))
        top = results[0]
        assert top.vector_score > 0 and top.bm25_score > 0
        assert top.channels  # 命中通道记录
        assert rel > 0.2, "on-topic 的 relevance 信号应高于拒答阈值"

    def test_offtopic_low_relevance(self, store):
        _res, rel = _search(store, "今天天气怎么样适合郊游", RetrievalFilters(permissions={"public", "internal"}))
        assert rel < 0.3


class TestReranker:
    def _retrieved(self, store):
        results, _ = _search(store, "session.timeout.ms 重平衡", RetrievalFilters(permissions={"public", "internal"}))
        return results

    def test_noop_preserves_order(self, store):
        results = self._retrieved(store)
        reranked = NoopReranker().rerank("session.timeout.ms", results)
        assert [r.chunk.id for r in reranked] == [r.chunk.id for r in results]
        assert all(r.rerank_score is not None for r in reranked)

    def test_llm_reranker_reorders(self, store):
        results = self._retrieved(store)
        llm = _ScriptedLLM("C: 9\nA: 1\nB: 1")
        reranked = LLMReranker(llm=llm).rerank("session.timeout.ms", results)
        assert reranked[0].chunk.id == "C"

    def test_llm_reranker_garbage_falls_back(self, store):
        results = self._retrieved(store)
        llm = _ScriptedLLM("无法评分")
        reranked = LLMReranker(llm=llm).rerank("session.timeout.ms", results)
        assert [r.chunk.id for r in reranked] == [r.chunk.id for r in results]


class _ScriptedLLM:
    def __init__(self, reply):
        self.reply = reply

    def chat(self, system, messages, **kw):
        return self.reply
