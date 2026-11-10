# -*- coding: utf-8 -*-
"""查询预处理测试:多轮指代改写 + 双语术语扩展(设计 §5.1/§5.2)。"""
from __future__ import annotations

from techdocs_rag.retrieval.rewriter import QueryRewriter


class FakeLLM:
    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    def chat(self, system, messages, **kw):
        self.calls.append(messages)
        return self.reply


class TestAnaphoraRewrite:
    def test_rule_rewrite_with_history(self):
        rw = QueryRewriter()
        r = rw.rewrite("那它的默认值是多少?", history=[{"role": "user", "content": "Kafka 消费者组 session.timeout.ms 是什么"}])
        assert "session.timeout.ms" in r.text
        assert "默认值" in r.text
        assert r.method == "rule_anaphora"

    def test_no_history_passthrough(self):
        rw = QueryRewriter()
        r = rw.rewrite("Kafka 重平衡触发条件有哪些", history=[])
        assert r.method == "passthrough"

    def test_llm_rewrite_short_query(self):
        llm = FakeLLM("Redis session timeout 默认值是多少")
        rw = QueryRewriter(llm=llm)
        r = rw.rewrite("默认值是多少", history=[{"role": "user", "content": "Redis 超时怎么配"}])
        assert r.method == "llm"
        assert "Redis" in r.text or "redis" in r.text
        assert llm.calls  # 确实走了 LLM


class TestTermExpansion:
    def test_zh_to_en(self):
        rw = QueryRewriter()
        r = rw.rewrite("消费者组重平衡怎么触发", history=[])
        assert "consumer group" in r.expansions
        assert "rebalance" in r.expansions
        assert "rebalance" in r.text

    def test_en_to_zh(self):
        rw = QueryRewriter()
        r = rw.rewrite("connection pool 怎么配置", history=[])
        assert "连接池" in r.expansions

    def test_no_false_expansion(self):
        rw = QueryRewriter()
        r = rw.rewrite("kafka topic 分区数设置", history=[])
        assert "连接池" not in r.expansions
