# -*- coding: utf-8 -*-
"""连接器抽象(设计 §2.2)。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SourceObject:
    id: str
    path: str = ""
    last_modified: str = ""
    etag: str = ""


@dataclass
class RawContent:
    source_id: str
    data: bytes
    last_modified: str = ""
    meta: dict = field(default_factory=dict)


@dataclass
class Cursor:
    value: Any = None
    kind: str = "updated_at"


class BaseSourceConnector(ABC):
    @abstractmethod
    def discover(self) -> list:
        """返回源中所有可同步对象。"""

    @abstractmethod
    def fetch(self, source_id: str) -> RawContent:
        """拉取原始内容(bytes + last_modified + etag)。"""

    @abstractmethod
    def get_incremental_cursor(self):
        """增量同步游标(updated_at 或 commit SHA)。"""

    @abstractmethod
    def map_metadata(self, raw: RawContent, source: SourceObject) -> dict:
        """统一元数据;缺失必填字段由管线校验拒收(设计 §2.3)。"""
