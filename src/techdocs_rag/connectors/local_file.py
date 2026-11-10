# -*- coding: utf-8 -*-
"""本地文件连接器:front-matter 优先,目录规则次之,默认值兜底(设计 §2.2 排期 1)。"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from techdocs_rag.connectors.base import BaseSourceConnector, Cursor, RawContent, SourceObject
from techdocs_rag.ingestion.parser import split_front_matter

DEFAULTS = {
    "source_type": "local_file",
    "authority_level": "authoritative",
    "doc_type": "guide",
    "permission_scope": "public",
    "version": "unknown",
}


class LocalFileConnector(BaseSourceConnector):
    EXTENSIONS = (".md", ".markdown", ".txt")

    def __init__(self, root, rules=None, defaults=None):
        self.root = str(root)
        self.rules = list(rules or [])
        self.defaults = dict(DEFAULTS)
        self.defaults.update(defaults or {})

    def discover(self) -> list:
        objects = []
        for dirpath, _dirs, files in os.walk(self.root):
            for fname in sorted(files):
                if not fname.endswith(self.EXTENSIONS):
                    continue
                full = os.path.join(dirpath, fname)
                rel = os.path.relpath(full, self.root).replace(os.sep, "/")
                objects.append(
                    SourceObject(
                        id=rel,
                        path=full,
                        last_modified=datetime.fromtimestamp(
                            os.path.getmtime(full), tz=timezone.utc
                        ).isoformat(),
                    )
                )
        return objects

    def fetch(self, source_id: str) -> RawContent:
        full = os.path.join(self.root, *source_id.split("/"))
        if not os.path.isfile(full):
            raise FileNotFoundError(source_id)
        with open(full, "rb") as f:
            data = f.read()
        text = data.decode("utf-8", errors="replace")
        fm, _body = split_front_matter(text)
        return RawContent(
            source_id=source_id,
            data=data,
            last_modified=datetime.fromtimestamp(
                os.path.getmtime(full), tz=timezone.utc
            ).isoformat(),
            meta={"front_matter": fm or {}},
        )

    def get_incremental_cursor(self):
        objects = self.discover()
        if not objects:
            return Cursor(value=None)
        return Cursor(value=max(o.last_modified for o in objects), kind="updated_at")

    def map_metadata(self, raw: RawContent, source: SourceObject) -> dict:
        meta = dict(self.defaults)
        for prefix, overrides in self.rules:
            if source.id.startswith(prefix):
                meta.update(overrides)
        meta.update(raw.meta.get("front_matter") or {})
        meta["source_id"] = source.id
        meta["last_modified"] = raw.last_modified
        return meta
