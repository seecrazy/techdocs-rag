# -*- coding: utf-8 -*-
"""查询路由测试:关键词规则/多栈/版本提取/LLM 兜底/全量兜底(设计 §6.1、§5.3)。"""
from __future__ import annotations

from techdocs_rag.retrieval.router import ALL_STACKS, route


class FakeLLM:
    def __init__(self, reply):
        self.reply = reply

    def chat(self, system, messages, **kw):
        return self.reply


class TestRulesRouting:
    def test_kafka(self):
        r = route("kafka consumer group rebalance 怎么处理")
        assert r.stacks == ["kafka"] and r.method == "rules" and r.confidence > 0.6

    def test_k8s(self):
        r = route("kubectl get pods CrashLoopBackOff 怎么排查")
        assert r.stacks == ["k8s"]

    def test_spring(self):
        r = route("Spring @Bean 注入失败怎么排查")
        assert r.stacks == ["spring"]

    def test_database(self):
        r = route("MySQL 死锁 deadlock 排查")
        assert r.stacks == ["database"]

    def test_multi_stack(self):
        r = route("kubectl 部署 Spring Boot 应用到 k8s 集群")
        assert set(r.stacks) == {"k8s", "spring"}

    def test_single_generic_mention_not_routed(self):
        # 单个非品牌词不应触发规则路由
        r = route("服务启动失败怎么办")
        assert r.method != "rules"


class TestVersionExtraction:
    def test_stack_prefixed_version(self):
        r = route("k8s 1.28 里 sidecar 容器怎么配置")
        assert r.version == "1.28" and r.stacks == ["k8s"]

    def test_bare_version_word(self):
        r = route("kafka 版本 3.6 的消费者配置")
        assert r.version == "3.6" and r.stacks == ["kafka"]

    def test_no_version(self):
        r = route("kafka consumer group 配置")
        assert r.version is None


class TestFallback:
    def test_fallback_all_without_llm(self):
        r = route("这个方案整体怎么落地")
        assert r.method == "fallback_all" and r.stacks == ALL_STACKS and r.confidence <= 0.5

    def test_llm_fallback(self):
        llm = FakeLLM('{"tech_stack": ["redis"], "confidence": 0.9}')
        r = route("持久化快照文件太大怎么办", llm=llm)
        assert r.stacks == ["redis"] and r.method == "llm"

    def test_llm_low_confidence_falls_back(self):
        llm = FakeLLM('{"tech_stack": ["redis"], "confidence": 0.3}')
        r = route("持久化快照文件太大怎么办", llm=llm)
        assert r.method == "fallback_all"

    def test_llm_garbage_falls_back(self):
        llm = FakeLLM("我认为应该是 redis 吧")
        r = route("持久化快照文件太大怎么办", llm=llm)
        assert r.method == "fallback_all"


class TestDocTypeHint:
    def test_troubleshooting(self):
        r = route("redis 报错 timeout 排查")
        assert r.doc_type_hint == "troubleshooting"

    def test_api_reference(self):
        r = route("kafka consumer 的 api 参数说明")
        assert r.doc_type_hint == "api_reference"

    def test_guide(self):
        r = route("kafka consumer group 怎么配置")
        assert r.doc_type_hint == "guide"
