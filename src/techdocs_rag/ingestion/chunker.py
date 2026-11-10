# -*- coding: utf-8 -*-
"""结构感知切分:标题路径、代码块/表格原子、父子分块、重叠、废弃标记(设计 §3)。"""
from __future__ import annotations

from techdocs_rag.config import ChunkSizeConfig
from techdocs_rag.ingestion.parser import Block
from techdocs_rag.models import DEPRECATED_MARKERS, Chunk, ChunkMetadata
from techdocs_rag.text import approx_tokens


class StructureAwareChunker:
    def __init__(self, chunking: dict):
        self.chunking = chunking

    def chunk(self, blocks: list, meta: dict) -> list:
        doc_type = meta.get("doc_type", "other")
        cfg = self.chunking.get(doc_type) or self.chunking["other"]
        source_id = meta["source_id"]
        out = []
        for path, sec_blocks in self._sections(blocks):
            units = self._units(sec_blocks)
            if not units:
                continue
            section_text = "\n\n".join(u.text for u in units)
            header = path + "\n"
            total = approx_tokens(header + section_text)
            deprecated = any(m in section_text.lower() for m in DEPRECATED_MARKERS)
            base = dict(meta)
            base["section"] = path
            base["deprecated"] = deprecated
            if total <= cfg.max_tokens:
                texts, parent_id = [header + "\n" + section_text], None
            else:
                texts = self._pack(units, cfg, header)
                parent_id = Chunk.make_id(source_id, path, "parent")
                out.append(
                    Chunk(
                        parent_id,
                        header + "\n" + section_text,
                        ChunkMetadata.from_dict({**base, "is_parent": True}),
                    )
                )
            for i, text in enumerate(texts):
                cmeta = ChunkMetadata.from_dict({**base, "parent_id": parent_id})
                out.append(Chunk(Chunk.make_id(source_id, path, i), text, cmeta))
        return out

    # -- 内部 -------------------------------------------------------------

    def _sections(self, blocks: list):
        """按标题切节;路径 = 标题栈。首个标题前的内容归入『正文』。"""
        stack, sections = [], []
        cur_path, cur = "正文", []
        for b in blocks:
            if b.type == "heading":
                sections.append((cur_path, cur))
                cur = []
                while stack and stack[-1][0] >= b.level:
                    stack.pop()
                stack.append((b.level, b.text))
                cur_path = " > ".join(t for _, t in stack)
            else:
                cur.append(b)
        sections.append((cur_path, cur))
        return [(p, bs) for p, bs in sections if bs]

    def _units(self, blocks: list) -> list:
        """原子单元:代码/表格/列表/段落;代码块重新围栏并保留语言标识。"""
        units = []
        for b in blocks:
            if b.type == "code":
                text = "```%s\n%s\n```" % (b.lang, b.text)
            else:
                text = b.text
            units.append(Block(b.type, text, level=b.level, lang=b.lang))
        return units

    def _pack(self, units: list, cfg: ChunkSizeConfig, header: str) -> list:
        """贪心装包;子块上限 max_tokens(含重叠可略超 max+overlap);代码/表格永不切分。"""
        hcost = approx_tokens(header)
        texts, buf, cost = [], [], hcost
        for u in units:
            uc = approx_tokens(u.text)
            if buf and cost + uc > cfg.max_tokens:
                texts.append(header + "\n\n" + "\n\n".join(b.text for b in buf))
                carry, cc = [], 0
                for b in reversed(buf):
                    if b.type not in ("paragraph", "list"):
                        break
                    bc = approx_tokens(b.text)
                    if cc + bc > cfg.overlap:
                        break
                    carry.insert(0, b)
                    cc += bc
                buf, cost = carry, hcost + cc
            buf.append(u)
            cost += uc
        if buf:
            texts.append(header + "\n\n" + "\n\n".join(b.text for b in buf))
        return texts
