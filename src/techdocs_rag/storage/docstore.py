# -*- coding: utf-8 -*-
"""文档级元数据与同步报告存储(设计 §2.4/§2.5、§6.5 family 聚合)。"""
from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import datetime, timezone

_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    source_id TEXT PRIMARY KEY,
    family_key TEXT NOT NULL,
    tech_stack TEXT NOT NULL,
    collection TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    last_modified TEXT,
    version TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    chunk_count INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_documents_family ON documents(family_key);
CREATE TABLE IF NOT EXISTS sync_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    source TEXT,
    added INTEGER, updated INTEGER, deleted INTEGER,
    failed INTEGER, quarantined INTEGER,
    details TEXT
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_version(version: str) -> tuple:
    """数值元组比较:1.28 > 1.9(禁止字符串比较,设计 §6.5)。"""
    if not version or version == "unknown":
        return ()
    return tuple(int(x) for x in re.findall(r"\d+", version))


class DocStore:
    def __init__(self, path):
        os.makedirs(os.path.dirname(str(path)) or ".", exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    def upsert(self, doc: dict) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO documents"
            "(source_id, family_key, tech_stack, collection, content_hash, last_modified,"
            " version, status, chunk_count, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                doc["source_id"],
                doc.get("family_key", ""),
                doc.get("tech_stack", ""),
                doc.get("collection", ""),
                doc.get("content_hash", ""),
                doc.get("last_modified", ""),
                doc.get("version", "unknown"),
                doc.get("status", "active"),
                doc.get("chunk_count", 0),
                _now(),
            ),
        )
        self.conn.commit()

    def get(self, source_id: str):
        row = self.conn.execute(
            "SELECT * FROM documents WHERE source_id=?", (source_id,)
        ).fetchone()
        return dict(row) if row else None

    def active_source_ids(self) -> set:
        rows = self.conn.execute("SELECT source_id FROM documents WHERE status='active'").fetchall()
        return {r["source_id"] for r in rows}

    def mark_deleted(self, source_id: str) -> None:
        self.conn.execute(
            "UPDATE documents SET status='deleted', updated_at=? WHERE source_id=?",
            (_now(), source_id),
        )
        self.conn.commit()

    def latest_family_versions(self) -> dict:
        """family_key → 最新版本(仅 active 文档;unknown 版本不参与)。"""
        rows = self.conn.execute(
            "SELECT family_key, version FROM documents WHERE status='active'"
        ).fetchall()
        latest = {}
        for r in rows:
            fam, ver = r["family_key"], r["version"]
            if not fam or ver == "unknown":
                continue
            cur = latest.get(fam)
            if cur is None or parse_version(ver) > parse_version(cur):
                latest[fam] = ver
        return latest

    def record_sync(self, report) -> None:
        self.conn.execute(
            "INSERT INTO sync_runs(ts, source, added, updated, deleted, failed, quarantined, details)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (
                _now(),
                report.source,
                report.added,
                report.updated,
                report.deleted,
                report.failed,
                report.quarantined,
                json.dumps(report.details, ensure_ascii=False)[:4000],
            ),
        )
        self.conn.commit()

    def recent_syncs(self, limit=10) -> list:
        rows = self.conn.execute(
            "SELECT * FROM sync_runs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
