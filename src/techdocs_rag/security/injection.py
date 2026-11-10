# -*- coding: utf-8 -*-
"""文档侧 Prompt Injection 扫描(设计 §8.1,中英双语模式)。"""
from __future__ import annotations

import re

SUSPECT_PATTERNS = [
    r"ignore\s+(?:all\s+|any\s+)?(?:previous|prior|above|earlier)\s+(?:instructions?|prompts?|rules?)",
    r"disregard\s+(?:the\s+|all\s+|any\s+)*(?:system|previous|above|earlier)\s+(?:prompt|instructions?|rules?)",
    r"act\s+as\s+(?:a|an|if)\b.*(?:ignore|override|bypass)",
    r"reveal\s+(?:your|the)\s+(?:system\s+)?prompt",
    r"忽略(?:以上|之前|上面|前面|上述)(?:的)?(?:所有|全部|任何)?(?:指令|提示|规则|要求|内容)",
    r"无视(?:以上|之前|上述)(?:的)?(?:所有|全部)?(?:指令|提示|规则)",
    r"(?:请|现在请|你要?|接下来)扮演.{0,10}(?:角色|人物|助手|身份)",
    r"输出(?:你的)?(?:完整)?系统提示词",
    r"^\s*system\s*[:：]\s*\S+",
    r"\bnew\s+instructions?\s*[:：]",
]

_COMPILED = [re.compile(p, re.IGNORECASE | re.MULTILINE) for p in SUSPECT_PATTERNS]


def scan(text: str) -> bool:
    if not text:
        return False
    low = text.lower()
    return any(p.search(low) for p in _COMPILED)
