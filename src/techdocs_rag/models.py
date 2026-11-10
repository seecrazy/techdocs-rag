# -*- coding: utf-8 -*-
"""核心数据模型与元数据强校验(设计 §2.3)。"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Optional

TECH_STACKS = ("k8s", "kafka", "redis", "spring", "database", "cross", "unknown")
DOC_TYPES = (
    "api_reference",
    "guide",
    "troubleshooting",
    "changelog",
    "code_example",
    "table",
    "other",
)
AUTHORITY_LEVELS = ("authoritative", "operational", "external")
SOURCE_TYPES = ("git_repo", "confluence", "ticket", "web", "local_file")

AUTHORITY_WEIGHT = {"authoritative": 1.0, "operational": 0.85, "external": 0.7}

DEPRECATED_MARKERS = ("deprecated", "已废弃", "不推荐使用", "breaking change")


class MetadataError(ValueError):
    pass


@dataclass
class ChunkMetadata:
    source_id: str = ""
    source_type: str = ""
    tech_stack: str = ""
    doc_type: str = ""
    authority_level: str = ""
    version: str = "unknown"
    content_hash: str = ""
    last_modified: str = ""
    permission_scope: str = "public"
    family_key: str = ""
    section: str = ""
    language: str = ""
    embedding_model: str = ""
    is_parent: bool = False
    parent_id: Optional[str] = None
    deprecated: bool = False
    superseded: bool = False
    injection_suspect: bool = False

    _REQUIRED = ("source_id", "source_type", "tech_stack", "doc_type", "authority_level")
    _ENUMS = {
        "tech_stack": TECH_STACKS,
        "doc_type": DOC_TYPES,
        "authority_level": AUTHORITY_LEVELS,
        "source_type": SOURCE_TYPES,
    }

    def validate(self) -> None:
        """必填缺失或枚举非法即拒绝入库(设计 §2.3)。"""
        for name in self._REQUIRED:
            if not getattr(self, name):
                raise MetadataError("missing required metadata field: %s" % name)
        for name, allowed in self._ENUMS.items():
            value = getattr(self, name)
            if value not in allowed:
                raise MetadataError(
                    "invalid %s=%r (allowed: %s)" % (name, value, ", ".join(allowed))
                )

    @classmethod
    def from_dict(cls, data: dict) -> "ChunkMetadata":
        meta = cls()
        for key, value in data.items():
            if key == "version" and isinstance(value, float):
                value = str(value)
            if hasattr(meta, key) and not key.startswith("_"):
                setattr(meta, key, value)
        return meta

    def as_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class Chunk:
    id: str
    text: str
    metadata: ChunkMetadata = field(default_factory=ChunkMetadata)
    embedding: Optional[list] = None

    @staticmethod
    def make_id(source_id: str, section: str, idx) -> str:
        raw = "%s#%s#%s" % (source_id, section, idx)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


@dataclass
class RetrievedChunk:
    chunk: Chunk
    fused_score: float = 0.0
    vector_score: float = 0.0
    bm25_score: float = 0.0
    channels: list = field(default_factory=list)
    rerank_score: Optional[float] = None

    @property
    def source_id(self) -> str:
        return self.chunk.metadata.source_id


@dataclass
class Citation:
    source_id: str
    section: str = ""
    valid: bool = True


@dataclass
class AnswerResult:
    answer: str
    refused: bool = False
    citations: list = field(default_factory=list)
    routing: dict = field(default_factory=dict)
    context_chunk_ids: list = field(default_factory=list)
    warning: str = ""
    trace_id: str = ""


@dataclass
class SyncReport:
    source: str
    added: int = 0
    updated: int = 0
    deleted: int = 0
    failed: int = 0
    quarantined: int = 0
    details: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return dict(self.__dict__)
