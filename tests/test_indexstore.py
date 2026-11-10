# -*- coding: utf-8 -*-
"""存储层测试:SQLite chunk store 持久化、内存向量/BM25 索引、谓词过滤(设计 §4)。"""
from __future__ import annotations

import math

from techdocs_rag.embeddings import HashEmbedder
from techdocs_rag.models import Chunk, ChunkMetadata
from techdocs_rag.storage.chunkstore import SQLiteChunkStore
from techdocs_rag.storage.indexstore import IndexStore


def make_chunk(cid, text, embedding=None, **meta):
    base = dict(
        source_id="kafka/consumer.md",
        source_type="local_file",
        tech_stack="kafka",
        doc_type="guide",
        authority_level="authoritative",
        section="s",
    )
    base.update(meta)
    return Chunk(cid, text, ChunkMetadata.from_dict(base), embedding)


def _cos(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return dot / (na * nb)


class TestHashEmbedder:
    def test_deterministic_and_normalized(self):
        e = HashEmbedder()
        a = e.embed_texts(["消费者组重平衡触发"])[0]
        b = e.embed_texts(["消费者组重平衡触发"])[0]
        assert a == b
        assert abs(math.sqrt(sum(x * x for x in a)) - 1.0) < 1e-6

    def test_similar_beats_dissimilar(self):
        e = HashEmbedder()
        a, b, c = e.embed_texts(["消费者组重平衡触发条件", "消费者组重平衡的触发条件说明", "今天天气不错适合散步"])
        assert _cos(a, b) > _cos(a, c)

    def test_name_and_dim(self):
        e = HashEmbedder(dim=64)
        assert e.name == "hash-64"
        assert len(e.embed_texts(["x"])[0]) == 64


class TestIndexStore:
    def _store(self, tmp_path):
        return IndexStore(SQLiteChunkStore(tmp_path / "chunks.db"))

    def test_vector_search_ranking(self, tmp_path):
        s = self._store(tmp_path)
        s.upsert_chunks(
            "collection_kafka",
            [
                make_chunk("c1", "向量A", embedding=[1.0, 0.0, 0.0]),
                make_chunk("c2", "向量B", embedding=[0.0, 1.0, 0.0]),
            ],
        )
        hits = s.vector_search("collection_kafka", [1.0, 0.1, 0.0], k=2)
        assert hits[0][0] == "c1" and hits[0][1] > 0.9

    def test_bm25_exact_term(self, tmp_path):
        s = self._store(tmp_path)
        s.upsert_chunks(
            "collection_kafka",
            [
                make_chunk("c1", "session.timeout.ms=45000 会话超时配置"),
                make_chunk("c2", "心跳间隔 heartbeat.interval.ms=3000"),
            ],
        )
        hits = s.bm25_search("collection_kafka", "session.timeout.ms 默认值", k=2)
        assert hits and hits[0][0] == "c1"

    def test_predicate_filters_permission(self, tmp_path):
        s = self._store(tmp_path)
        s.upsert_chunks(
            "collection_kafka",
            [
                make_chunk("pub", "session.timeout.ms 公开内容", embedding=[1, 0], permission_scope="public"),
                make_chunk("int", "session.timeout.ms 内部内容", embedding=[1, 0], permission_scope="internal"),
            ],
        )
        internal_only = s.bm25_search(
            "collection_kafka", "session.timeout.ms", k=5, pred=lambda m: m.permission_scope == "internal"
        )
        assert [h[0] for h in internal_only] == ["int"]
        vec_hits = s.vector_search("collection_kafka", [1, 0], k=5, pred=lambda m: m.permission_scope == "internal")
        assert [h[0] for h in vec_hits] == ["int"]

    def test_parent_not_indexed_but_stored(self, tmp_path):
        s = self._store(tmp_path)
        s.upsert_chunks(
            "collection_kafka",
            [
                make_chunk("p1", "父块完整内容 session.timeout.ms", is_parent=True),
                make_chunk("k1", "子块 session.timeout.ms", embedding=[1, 0], parent_id="p1"),
            ],
        )
        assert s.bm25_search("collection_kafka", "session.timeout.ms", k=5)
        hits = s.bm25_search("collection_kafka", "session.timeout.ms", k=5)
        assert [h[0] for h in hits] == ["k1"]  # 父块不参与检索
        assert "p1" in s.get_chunks("collection_kafka", ["p1"])  # 但可按 id 取回

    def test_delete_by_source(self, tmp_path):
        s = self._store(tmp_path)
        s.upsert_chunks(
            "collection_kafka",
            [make_chunk("c1", "删除我 session.timeout.ms", embedding=[1, 0], source_id="kafka/a.md")],
        )
        s.delete_by_source("collection_kafka", "kafka/a.md")
        assert s.bm25_search("collection_kafka", "session.timeout.ms", k=5) == []
        assert s.get_chunks("collection_kafka", ["c1"]) == {}

    def test_persistence_rebuild(self, tmp_path):
        cs = SQLiteChunkStore(tmp_path / "chunks.db")
        s1 = IndexStore(cs)
        s1.upsert_chunks(
            "collection_kafka",
            [make_chunk("c1", "重启后仍可检索 session.timeout.ms", embedding=[1, 0])],
        )
        s2 = IndexStore(SQLiteChunkStore(tmp_path / "chunks.db"))
        hits = s2.bm25_search("collection_kafka", "session.timeout.ms", k=5)
        assert hits and hits[0][0] == "c1"
        vh = s2.vector_search("collection_kafka", [1, 0], k=5)
        assert vh and vh[0][0] == "c1"

    def test_stats(self, tmp_path):
        s = self._store(tmp_path)
        s.upsert_chunks(
            "collection_kafka",
            [
                make_chunk("c1", "内容", embedding=[1, 0]),
                make_chunk("p1", "父块", is_parent=True),
            ],
        )
        stats = s.stats()
        assert stats["collection_kafka"]["chunks"] == 1
        assert stats["collection_kafka"]["parents"] == 1
