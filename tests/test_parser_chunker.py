# -*- coding: utf-8 -*-
"""结构感知切分测试(设计 §3:代码块/表格原子、标题路径、父子分块、重叠、废弃标记)。"""
from __future__ import annotations

from techdocs_rag.config import CHUNKING_DEFAULTS, ChunkSizeConfig, load_config
from techdocs_rag.ingestion.chunker import StructureAwareChunker
from techdocs_rag.ingestion.parser import MarkdownParser, split_front_matter

DOC = """# Kafka 消费者指南

## 消费者组机制
消费者组(consumer group)由多个消费者实例组成,partition 只能被组内一个消费者消费。

## 重平衡触发条件
成员变化、分区数变化、session.timeout.ms 超时(默认 45000ms)会触发重平衡。

```properties
session.timeout.ms=45000
heartbeat.interval.ms=3000
partition.assignment.strategy=cooperative-sticky
```

## 参数表
| 参数 | 默认值 | 说明 |
|---|---|---|
| session.timeout.ms | 45000 | 会话超时 |
| heartbeat.interval.ms | 3000 | 心跳间隔 |
"""

META = dict(
    source_id="kafka/consumer.md",
    source_type="local_file",
    tech_stack="kafka",
    doc_type="guide",
    authority_level="authoritative",
)


def _chunks(doc=DOC, meta=None, cfg=None):
    meta = dict(META, **(meta or {}))
    fm, body = split_front_matter(doc)
    blocks = MarkdownParser().parse(body)
    chunker = StructureAwareChunker(cfg or load_config(None).chunking)
    return chunker.chunk(blocks, meta)


class TestFrontMatter:
    def test_split_and_parse(self):
        doc = '---\nversion: "3.6"\ntech_stack: kafka\n---\n\n# T\n正文'
        fm, body = split_front_matter(doc)
        assert fm == {"version": "3.6", "tech_stack": "kafka"}
        assert "# T" in body

    def test_no_front_matter(self):
        fm, body = split_front_matter("# T\n正文")
        assert fm is None and "# T" in body


class TestParser:
    def test_block_types(self):
        _, body = split_front_matter(DOC)
        blocks = MarkdownParser().parse(body)
        types = [b.type for b in blocks]
        assert "heading" in types and "code" in types and "table" in types
        code = next(b for b in blocks if b.type == "code")
        assert code.lang == "properties"
        assert "session.timeout.ms=45000" in code.text
        table = next(b for b in blocks if b.type == "table")
        assert "| session.timeout.ms | 45000" in table.text


class TestChunker:
    def test_section_path_in_metadata_and_prefix(self):
        chunks = _chunks()
        paths = {c.metadata.section for c in chunks}
        assert any("消费者组机制" in p for p in paths)
        assert any("重平衡触发条件" in p for p in paths)
        body_chunk = next(c for c in chunks if "成员变化" in c.text)
        assert "重平衡触发条件" in body_chunk.text  # 正文前缀携带标题路径

    def test_code_block_atomic_and_fence_kept(self):
        chunks = _chunks()
        hits = [c for c in chunks if "session.timeout.ms=45000" in c.text]
        assert len(hits) >= 1
        for c in hits:
            assert "cooperative-sticky" in c.text  # 代码块整体在同一个 chunk
            assert "```properties" in c.text  # 语言标识保留

    def test_table_atomic(self):
        chunks = _chunks()
        hits = [c for c in chunks if "会话超时" in c.text]
        assert hits
        hit = hits[0]
        assert "| session.timeout.ms | 45000 | 会话超时 |" in hit.text

    def test_parent_child(self):
        # 用极小的块上限强制一个大章节产生多个子块
        cfg = {
            "guide": ChunkSizeConfig(max_tokens=24, parent_max_tokens=10_000, overlap=0),
            "other": ChunkSizeConfig(max_tokens=24, parent_max_tokens=10_000, overlap=0),
        }
        chunks = _chunks(cfg=cfg)
        parents = [c for c in chunks if c.metadata.is_parent]
        children = [c for c in chunks if not c.metadata.is_parent and c.metadata.parent_id]
        assert parents and children
        parent_ids = {p.id for p in parents}
        assert all(c.metadata.parent_id in parent_ids for c in children)
        # 父块包含子块全部内容(章节级)
        for p in parents:
            kids = [c for c in children if c.metadata.parent_id == p.id]
            for k in kids:
                core = k.text.split("\n\n", 1)[1] if "\n\n" in k.text else k.text
                assert core.strip() in p.text

    def test_overlap_between_splits(self):
        para = "\n\n".join(f"第{i}段:" + "配置说明文字" * 8 for i in range(10))
        doc = f"# 指南\n\n## 配置\n{para}"
        cfg = {"guide": ChunkSizeConfig(max_tokens=60, parent_max_tokens=100_000, overlap=40)}
        chunks = _chunks(doc=doc, cfg=cfg)
        kids = [c for c in chunks if "配置" in c.metadata.section and "段" in c.text]
        assert len(kids) >= 2
        # 相邻子块存在共享文本(重叠)
        shared = False
        for a, b in zip(kids, kids[1:]):
            a_tail = a.text[-60:]
            if any(line.strip and line.strip() in b.text for line in a_tail.splitlines() if line.strip()):
                shared = True
        assert shared

    def test_deprecated_flag(self):
        doc = "# 指南\n\n## 旧接口\n该接口已废弃(deprecated),请使用新接口。"
        chunks = _chunks(doc=doc, meta=dict(doc_type="guide"))
        flagged = [c for c in chunks if c.metadata.deprecated]
        assert flagged and all("旧接口" in c.metadata.section for c in flagged)

    def test_all_chunks_carry_base_metadata(self):
        for c in _chunks():
            c.metadata.validate()
            assert c.metadata.source_id == "kafka/consumer.md"
            assert c.metadata.tech_stack == "kafka"

    def test_chunking_defaults_cover_all_doc_types(self):
        for dt in ["api_reference", "guide", "troubleshooting", "changelog", "code_example", "table", "other"]:
            assert dt in CHUNKING_DEFAULTS
