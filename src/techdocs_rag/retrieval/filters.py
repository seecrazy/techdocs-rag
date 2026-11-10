# -*- coding: utf-8 -*-
"""检索过滤谓词:权限在通道内过滤;默认 latest;显式版本穿透(设计 §6.5/§6.6)。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class RetrievalFilters:
    permissions: set
    version: Optional[str] = None
    version_policy: str = "latest"  # latest | all
    doc_type_hint: Optional[str] = None
    exclude_external_suspect: bool = False


def build_filter(f: RetrievalFilters, family_latest: dict):
    """family_latest: family_key → 最新版本(DocStore.latest_family_versions())。"""

    def pred(m) -> bool:
        # 注入处置:external + suspect 不入检索结果(设计 §8.1 过滤层)
        if f.exclude_external_suspect and m.injection_suspect and m.authority_level == "external":
            return False
        # 权限过滤必须发生在检索阶段,生成端不做二次判断(设计 §6.6)
        if m.permission_scope not in f.permissions:
            return False
        if f.version:
            # 显式版本穿透:可命中 superseded 旧版本;unknown 不误杀
            return m.version == f.version or m.version == "unknown"
        if m.superseded:
            return False
        if f.version_policy == "latest":
            latest = family_latest.get(m.family_key)
            if latest and m.version != "unknown" and m.version != latest:
                return False
        return True

    return pred
