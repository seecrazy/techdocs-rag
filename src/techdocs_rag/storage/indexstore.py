# -*- coding: utf-8 -*-
"""统一索引门面:内存向量/BM25 索引 + SQLite 持久化;谓词过滤在通道内完成(设计 §4/§6.6)。"""
from __future__ import annotations

import math

from techdocs_rag.models import Chunk
from techdocs_rag.text import tokenize

_BM25_K1 = 1.5
_BM25_B = 0.75


def _cosine(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class _Collection:
    def __init__(self):
        self.chunks = {}  # id -> Chunk(含父块)
        self.tokens = {}  # id -> tokens(仅子块)


class IndexStore:
    def __init__(self, chunk_store):
        self.cs = chunk_store
        self.cols = {}
        self.rebuild()

    def rebuild(self) -> None:
        self.cols = {}
        for name in self.cs.collections():
            col = self.cols.setdefault(name, _Collection())
            for chunk in self.cs.all_chunks(name):
                self._index(col, chunk)

    def _col(self, name) -> _Collection:
        return self.cols.setdefault(name, _Collection())

    def _index(self, col, chunk: Chunk) -> None:
        col.chunks[chunk.id] = chunk
        if chunk.metadata.is_parent:
            col.tokens.pop(chunk.id, None)
        else:
            col.tokens[chunk.id] = tokenize(chunk.text)

    # -- 写入 ---------------------------------------------------------------

    def upsert_chunks(self, collection: str, chunks: list) -> None:
        col = self._col(collection)
        self.cs.upsert_many(collection, chunks)
        for c in chunks:
            self._index(col, c)

    def delete_by_source(self, collection: str, source_id: str) -> None:
        col = self._col(collection)
        stale = [i for i, c in col.chunks.items() if c.metadata.source_id == source_id]
        for i in stale:
            col.chunks.pop(i, None)
            col.tokens.pop(i, None)
        self.cs.delete_by_source(collection, source_id)

    # -- 检索 ---------------------------------------------------------------

    def vector_search(self, collection: str, vec, k: int, pred=None) -> list:
        col = self.cols.get(collection)
        if not col or not vec:
            return []
        scored = []
        for cid, chunk in col.chunks.items():
            if chunk.metadata.is_parent or chunk.embedding is None:
                continue
            if pred is not None and not pred(chunk.metadata):
                continue
            scored.append((cid, _cosine(vec, chunk.embedding)))
        scored.sort(key=lambda x: (-x[1], x[0]))
        return [(cid, s) for cid, s in scored[:k] if s > 0]

    def bm25_search(self, collection: str, query_text: str, k: int, pred=None) -> list:
        col = self.cols.get(collection)
        if not col:
            return []
        qtoks = tokenize(query_text)
        if not qtoks:
            return []
        docs = {
            cid: toks
            for cid, toks in col.tokens.items()
            if pred is None or pred(col.chunks[cid].metadata)
        }
        if not docs:
            return []
        n = len(docs)
        avgdl = sum(len(t) for t in docs.values()) / n or 1.0
        df = {}
        for toks in docs.values():
            for t in set(toks):
                df[t] = df.get(t, 0) + 1
        scored = []
        for cid, toks in docs.items():
            tf = {}
            for t in toks:
                tf[t] = tf.get(t, 0) + 1
            score = 0.0
            dl = len(toks)
            for t in qtoks:
                if t not in tf:
                    continue
                idf = math.log(1.0 + (n - df[t] + 0.5) / (df[t] + 0.5))
                denom = tf[t] + _BM25_K1 * (1.0 - _BM25_B + _BM25_B * dl / avgdl)
                score += idf * tf[t] * (_BM25_K1 + 1.0) / denom
            if score > 0:
                scored.append((cid, score))
        scored.sort(key=lambda x: (-x[1], x[0]))
        return scored[:k]

    def get_chunks(self, collection: str, ids: list) -> dict:
        col = self.cols.get(collection)
        if not col:
            return {}
        return {i: col.chunks[i] for i in ids if i in col.chunks}

    def stats(self) -> dict:
        return {
            name: {
                "chunks": len(col.tokens),
                "parents": sum(1 for c in col.chunks.values() if c.metadata.is_parent),
            }
            for name, col in self.cols.items()
        }
