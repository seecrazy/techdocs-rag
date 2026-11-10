# -*- coding: utf-8 -*-
"""接入管线:校验→切分→注入扫描→向量化→入库;文档级重切与删除传播(设计 §2.4/§2.5、§8.1)。"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone

from techdocs_rag.ingestion.parser import MarkdownParser, split_front_matter
from techdocs_rag.models import ChunkMetadata, MetadataError, SyncReport
from techdocs_rag.security.injection import scan

_VERSION_DIR = re.compile(r"/v\d+(?:\.\d+)*/")


def family_of(source_id: str) -> str:
    """去除路径中的版本目录段:kafka/v1.28/g.md → kafka/g.md(设计 §6.5)。"""
    return _VERSION_DIR.sub("/", source_id)


class IngestionPipeline:
    def __init__(self, index_store, doc_store, chunker, embedder, config, parser=None):
        self.index_store = index_store
        self.doc_store = doc_store
        self.chunker = chunker
        self.embedder = embedder
        self.config = config
        self.parser = parser or MarkdownParser()

    def sync(self, connector) -> SyncReport:
        report = SyncReport(source=self._source_name(connector))
        objects = {o.id: o for o in connector.discover()}
        for oid, obj in objects.items():
            try:
                change = self._ingest_one(connector, oid, obj, report)
            except MetadataError as e:
                report.failed += 1
                report.details.append({"source_id": oid, "error": "metadata: %s" % e})
            except Exception as e:  # noqa: BLE001
                report.failed += 1
                report.details.append({"source_id": oid, "error": str(e)})
            else:
                if change:
                    setattr(report, change, getattr(report, change) + 1)
        self._propagate_deletions(objects, report)
        self.doc_store.record_sync(report)
        return report

    # -- 单文档 -------------------------------------------------------------

    def _ingest_one(self, connector, oid, obj, report):
        raw = connector.fetch(oid)
        content_hash = hashlib.sha256(raw.data).hexdigest()
        prev = self.doc_store.get(oid)
        if prev and prev["status"] == "active" and prev["content_hash"] == content_hash:
            return None  # 未变化,幂等跳过

        text = raw.data.decode("utf-8", errors="replace")
        _fm, body = split_front_matter(text)
        meta = ChunkMetadata.from_dict(connector.map_metadata(raw, obj))
        meta.content_hash = content_hash
        meta.family_key = meta.family_key or family_of(oid)
        meta.validate()  # 必填/枚举强校验,缺失即拒收

        quarantined = meta.tech_stack == "unknown"
        collection = "collection_" + meta.tech_stack
        blocks = self.parser.parse(body)
        chunks = self.chunker.chunk(blocks, meta.as_dict())
        if not chunks:
            raise MetadataError("空文档或无可切分内容: %s" % oid)

        for c in chunks:
            c.metadata.content_hash = content_hash
            c.metadata.family_key = meta.family_key
            c.metadata.embedding_model = self.embedder.name
            if scan(c.text):
                c.metadata.injection_suspect = True

        children = [c for c in chunks if not c.metadata.is_parent]
        vectors = self.embedder.embed_texts([c.text for c in children])
        for c, vec in zip(children, vectors):
            c.embedding = vec

        self.index_store.delete_by_source(collection, oid)  # 文档级重切,禁止 chunk 级 diff
        self.index_store.upsert_chunks(collection, chunks)
        self.doc_store.upsert(
            {
                "source_id": oid,
                "family_key": meta.family_key,
                "tech_stack": meta.tech_stack,
                "collection": collection,
                "content_hash": content_hash,
                "last_modified": meta.last_modified,
                "version": meta.version,
                "status": "active",
                "chunk_count": len(children),
            }
        )
        if quarantined:
            report.quarantined += 1
            report.details.append({"source_id": oid, "quarantined": True})
        return "updated" if prev else "added"

    # -- 删除传播(设计 §2.4 验收③)---------------------------------------

    def _propagate_deletions(self, objects: dict, report: SyncReport) -> None:
        for sid in self.doc_store.active_source_ids():
            if sid in objects:
                continue
            doc = self.doc_store.get(sid)
            if not doc:
                continue
            self.index_store.delete_by_source(doc["collection"], sid)
            self.doc_store.mark_deleted(sid)
            report.deleted += 1
            report.details.append({"source_id": sid, "deleted": True})

    @staticmethod
    def _source_name(connector) -> str:
        return getattr(connector, "root", type(connector).__name__)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
