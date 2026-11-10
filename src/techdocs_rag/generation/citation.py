# -*- coding: utf-8 -*-
"""引用运行期校验:提取 → 与注入片段比对 → 移除编造引用并警告(设计 §7.3)。"""
from __future__ import annotations

import re

from techdocs_rag.models import Citation

_CITE = re.compile(
    r"\[来源[:：]\s*([^,\]】]+?)\s*"
    r"(?:[,，]\s*章节[:：]\s*([^\]】]*?))?\s*"
    r"(?:[,，]\s*版本[:：]\s*([^\]】]*?))?\s*\]"
)


def extract_citations(answer: str) -> list:
    return [
        Citation(m.group(1).strip(), (m.group(2) or "").strip(), True)
        for m in _CITE.finditer(answer)
    ]


def validate_and_clean(answer: str, allowed_source_ids):
    """返回 (清洗后答案, 全部引用, 无效引用数)。无效引用从答案移除并附警告。"""
    allowed = set(allowed_source_ids)
    citations, invalid_spans = [], []
    for m in _CITE.finditer(answer):
        source_id = m.group(1).strip()
        valid = source_id in allowed
        citations.append(Citation(source_id, (m.group(2) or "").strip(), valid))
        if not valid:
            invalid_spans.append(m.group(0))
    clean = answer
    for span in invalid_spans:
        clean = clean.replace(span, "")
    if invalid_spans:
        clean = clean.rstrip() + "\n\n> ⚠ 有 %d 处引用未通过校验,已移除。" % len(invalid_spans)
    return clean, citations, len(invalid_spans)
