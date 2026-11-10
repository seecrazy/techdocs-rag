# -*- coding: utf-8 -*-
"""Markdown 结构解析:front-matter / 标题 / 段落 / 代码块 / 表格 / 列表(设计 §3)。"""
from __future__ import annotations

import re
from dataclasses import dataclass

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+")


@dataclass
class Block:
    type: str  # heading | paragraph | code | table | list
    text: str
    level: int = 0
    lang: str = ""


def split_front_matter(text: str):
    """返回 (front_matter dict | None, 正文)。front-matter 中的版本号务必加引号。"""
    if not text.startswith("---"):
        return None, text
    lines = text.splitlines()
    if lines[0].strip() != "---":
        return None, text
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            raw = "\n".join(lines[1:i])
            if yaml is None:  # pragma: no cover
                return None, "\n".join(lines[i + 1 :])
            try:
                fm = yaml.safe_load(raw)
            except yaml.YAMLError:
                fm = None
            if not isinstance(fm, dict):
                fm = None
            return fm, "\n".join(lines[i + 1 :])
    return None, text


class MarkdownParser:
    """逐行扫描,产出结构块;代码块与表格作为不可分割的整体内容(含围栏)。"""

    def parse(self, text: str) -> list:
        blocks = []
        lines = text.splitlines()
        i, n = 0, len(lines)
        while i < n:
            line = lines[i]
            stripped = line.strip()
            if not stripped:
                i += 1
                continue
            m = _HEADING.match(line)
            if m:
                blocks.append(Block("heading", m.group(2).strip(), level=len(m.group(1))))
                i += 1
                continue
            if stripped.startswith("```") or stripped.startswith("~~~"):
                fence = stripped[:3]
                lang = stripped[3:].strip()
                buf = [line]
                i += 1
                while i < n and not lines[i].strip().startswith(fence):
                    buf.append(lines[i])
                    i += 1
                if i < n:
                    buf.append(lines[i])
                    i += 1
                inner = "\n".join(buf[1:-1]) if len(buf) > 2 else ""
                blocks.append(Block("code", inner, lang=lang))
                continue
            if stripped.startswith("|"):
                buf = []
                while i < n and lines[i].strip().startswith("|"):
                    buf.append(lines[i].strip())
                    i += 1
                blocks.append(Block("table", "\n".join(buf)))
                continue
            if _LIST_ITEM.match(line):
                buf = []
                while i < n and _LIST_ITEM.match(lines[i]):
                    buf.append(lines[i].rstrip())
                    i += 1
                blocks.append(Block("list", "\n".join(buf)))
                continue
            buf = []
            while i < n:
                s = lines[i].strip()
                if (
                    not s
                    or _HEADING.match(lines[i])
                    or s.startswith("```")
                    or s.startswith("~~~")
                    or s.startswith("|")
                    or _LIST_ITEM.match(lines[i])
                ):
                    break
                buf.append(lines[i].rstrip())
                i += 1
            blocks.append(Block("paragraph", " ".join(buf)))
        return blocks
