# -*- coding: utf-8 -*-
"""统一分词与 token 估算(设计 §6.3:双通道共用,错误码/点分配置键不可切碎)。"""
from __future__ import annotations

import re
from math import ceil

_ASCII = re.compile(r"[a-z0-9][a-z0-9_\-./]*")
_CJK_RUN = re.compile(r"[\u4e00-\u9fff]+")
_SUB_SPLIT = re.compile(r"[._\-/]+")
_ASCII_WORD = re.compile(r"[A-Za-z0-9_\-./]+")


def tokenize(text: str) -> list:
    """ASCII 词整体保留并派生子词(点分/下划线键),CJK 连续段切二元,统一小写。"""
    if not text:
        return []
    low = text.lower()
    tokens = []
    for m in _ASCII.finditer(low):
        full = m.group(0).strip("._-/")
        if not full:
            continue
        tokens.append(full)
        parts = _SUB_SPLIT.split(full)
        if len(parts) > 1:
            tokens.extend(p for p in parts if p)
    for run in _CJK_RUN.findall(low):
        if len(run) == 1:
            tokens.append(run)
        else:
            tokens.extend(run[i : i + 2] for i in range(len(run) - 1))
    return tokens


def approx_tokens(text: str) -> int:
    """粗略 token 估算:CJK 字符 0.6/字 + ASCII 词 1.3/词,向上取整。"""
    if not text:
        return 0
    cjk = sum(len(r) for r in _CJK_RUN.findall(text))
    words = len(_ASCII_WORD.findall(text))
    return ceil(cjk * 0.6 + words * 1.3)
