# -*- coding: utf-8 -*-
"""基础件测试:分词器 / 元数据校验 / 配置(设计 §2.3、§6.3)。"""
from __future__ import annotations

import pytest

from techdocs_rag.text import approx_tokens, tokenize
from techdocs_rag.models import (
    AUTHORITY_WEIGHT,
    Chunk,
    ChunkMetadata,
    MetadataError,
)


def _meta(**kw):
    base = dict(
        source_id="kafka/consumer.md",
        source_type="local_file",
        tech_stack="kafka",
        doc_type="guide",
        authority_level="authoritative",
    )
    base.update(kw)
    base = {k: v for k, v in base.items() if v is not None}
    return ChunkMetadata.from_dict(base)


class TestTokenizer:
    def test_error_code_not_split(self):
        toks = tokenize("错误码 E1024 出现")
        assert "e1024" in toks

    def test_config_key_yields_full_and_sub_tokens(self):
        toks = tokenize("spring.redis.timeout")
        assert "spring.redis.timeout" in toks
        assert {"spring", "redis", "timeout"} <= set(toks)

    def test_ascii_lowercased_whole(self):
        assert "getuserbyid" in tokenize("调用 getUserById 失败")

    def test_cjk_bigram(self):
        toks = tokenize("消费者组")
        assert "消费" in toks and "费者" in toks and "者组" in toks

    def test_single_cjk_char(self):
        assert tokenize("网") == ["网"]

    def test_empty(self):
        assert tokenize("") == []
        assert approx_tokens("") == 0

    def test_approx_tokens_grows_with_length(self):
        assert approx_tokens("hello world foo bar") > approx_tokens("hello")
        assert approx_tokens("这是一段比较长的中文说明文字用于估算") > approx_tokens("短文")


class TestChunkMetadata:
    def test_valid_passes(self):
        _meta().validate()

    @pytest.mark.parametrize("field", ["source_id", "source_type", "tech_stack", "doc_type", "authority_level"])
    def test_missing_required_raises(self, field):
        m = _meta(**{field: None})
        with pytest.raises(MetadataError):
            m.validate()

    @pytest.mark.parametrize(
        "field,value",
        [
            ("tech_stack", "docker"),
            ("authority_level", "semi"),
            ("source_type", "ftp"),
            ("doc_type", "novel"),
        ],
    )
    def test_invalid_enum_raises(self, field, value):
        with pytest.raises(MetadataError):
            _meta(**{field: value}).validate()

    def test_unknown_extra_keys_ignored(self):
        m = _meta()
        m2 = ChunkMetadata.from_dict({**_meta().__dict__, "bogus": 1})
        m2.validate()

    def test_authority_weight_values(self):
        assert AUTHORITY_WEIGHT == {"authoritative": 1.0, "operational": 0.85, "external": 0.7}


class TestChunkId:
    def test_stable_and_distinct(self):
        a = Chunk.make_id("a.md", "sec", 0)
        assert a == Chunk.make_id("a.md", "sec", 0)
        assert a != Chunk.make_id("a.md", "sec", 1)
        assert a != Chunk.make_id("b.md", "sec", 0)
