# -*- coding: utf-8 -*-
"""引用运行期校验测试(设计 §7.3)。"""
from __future__ import annotations

from techdocs_rag.generation.citation import extract_citations, validate_and_clean

A = "[来源: kafka/consumer.md, 章节: 4.2 重平衡, 版本: 3.6]"
B = "[来源: tickets/t1.md, 章节: 问题-解决]"


class TestExtract:
    def test_full_format(self):
        cites = extract_citations("重平衡由成员变化触发 %s。" % A)
        assert len(cites) == 1
        assert cites[0].source_id == "kafka/consumer.md"
        assert "重平衡" in cites[0].section and cites[0].valid

    def test_without_version(self):
        cites = extract_citations("见工单 %s 处理。" % B)
        assert cites[0].source_id == "tickets/t1.md"
        assert cites[0].section.startswith("问题")

    def test_multiple(self):
        answer = "官方说明 %s;工单补充 %s。" % (A, B)
        assert [c.source_id for c in extract_citations(answer)] == [
            "kafka/consumer.md",
            "tickets/t1.md",
        ]

    def test_none(self):
        assert extract_citations("普通回答,没有引用。") == []


class TestValidate:
    def test_valid_kept_verbatim(self):
        answer = "重平衡由成员变化触发 %s。" % A
        clean, cites, n_invalid = validate_and_clean(answer, {"kafka/consumer.md"})
        assert clean == answer
        assert n_invalid == 0 and cites[0].valid

    def test_invalid_removed_with_warning(self):
        ghost = "[来源: ghost.md, 章节: 1]"
        answer = "内容A %s;内容B %s。" % (A, ghost)
        clean, cites, n_invalid = validate_and_clean(answer, {"kafka/consumer.md"})
        assert "ghost.md" not in clean
        assert A in clean
        assert n_invalid == 1
        assert cites[1].valid is False
        assert "校验" in clean or "移除" in clean, "应向用户提示移除了无效引用"

    def test_all_invalid(self):
        answer = "x [来源: a.md, 章节: 1] y [来源: b.md, 章节: 2]"
        clean, cites, n_invalid = validate_and_clean(answer, {"c.md"})
        assert n_invalid == 2
        assert "a.md" not in clean and "b.md" not in clean

    def test_empty_allowed(self):
        clean, _cites, n_invalid = validate_and_clean("见 %s" % A, set())
        assert n_invalid == 1
