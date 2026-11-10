# -*- coding: utf-8 -*-
"""chunk 持久化(SQLite):进程重启后可重建内存索引(设计 §4.4)。"""
from __future__ import annotations

import json
import os
import sqlite3

from techdocs_rag.models import Chunk, ChunkMetadata

_SCHEMA = """
CREATE TABLE IF NOT EXISTS chunks (
    id TEXT NOT NULL,
    collection TEXT NOT NULL,
    source_id TEXT NOT NULL,
    is_parent INTEGER NOT NULL DEFAULT 0,
    text TEXT NOT NULL,
    metadata TEXT NOT NULL,
    embedding TEXT,
    PRIMARY KEY (collection, id)
);
CREATE INDEX IF NOT EXISTS idx_chunks_source ON chunks(collection, source_id);
"""


class SQLiteChunkStore:
    def __init__(self, path):
        os.makedirs(os.path.dirname(str(path)) or ".", exist_ok=True)
        # check_same_thread=False:FastAPI 线程池中访问;单进程开发规模下可接受
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    def upsert_many(self, collection: str, chunks: list) -> None:
        rows = [
            (
                c.id,
                collection,
                c.metadata.source_id,
                1 if c.metadata.is_parent else 0,
                c.text,
                json.dumps(c.metadata.as_dict(), ensure_ascii=False),
                json.dumps(c.embedding) if c.embedding is not None else None,
            )
            for c in chunks
        ]
        self.conn.executemany(
            "INSERT OR REPLACE INTO chunks"
            "(id, collection, source_id, is_parent, text, metadata, embedding)"
            " VALUES (?,?,?,?,?,?,?)",
            rows,
        )
        self.conn.commit()

    def delete_by_source(self, collection: str, source_id: str) -> None:
        self.conn.execute(
            "DELETE FROM chunks WHERE collection=? AND source_id=?", (collection, source_id)
        )
        self.conn.commit()

    def get_many(self, collection: str, ids: list) -> dict:
        out = {}
        for cid in ids:
            row = self.conn.execute(
                "SELECT id, text, metadata, embedding FROM chunks WHERE collection=? AND id=?",
                (collection, cid),
            ).fetchone()
            if row:
                out[cid] = self._row_to_chunk(row)
        return out

    def all_chunks(self, collection: str) -> list:
        rows = self.conn.execute(
            "SELECT id, text, metadata, embedding FROM chunks WHERE collection=?", (collection,)
        ).fetchall()
        return [self._row_to_chunk(r) for r in rows]

    def collections(self) -> list:
        rows = self.conn.execute("SELECT DISTINCT collection FROM chunks").fetchall()
        return [r[0] for r in rows]

    def stats(self) -> dict:
        rows = self.conn.execute(
            "SELECT collection, SUM(CASE WHEN is_parent=0 THEN 1 ELSE 0 END),"
            " SUM(CASE WHEN is_parent=1 THEN 1 ELSE 0 END)"
            " FROM chunks GROUP BY collection"
        ).fetchall()
        return {c: {"chunks": n or 0, "parents": p or 0} for c, n, p in rows}

    @staticmethod
    def _row_to_chunk(row) -> Chunk:
        cid, text, meta_json, emb_json = row
        embedding = json.loads(emb_json) if emb_json else None
        return Chunk(cid, text, ChunkMetadata.from_dict(json.loads(meta_json)), embedding)
