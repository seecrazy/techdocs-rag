# -*- coding: utf-8 -*-
"""查询路由:关键词规则 → LLM 分类 → 全量兜底;版本与 doc_type 意图提取(设计 §6.1、§5.3)。"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Optional

from techdocs_rag.models import TECH_STACKS

ALL_STACKS = ["k8s", "kafka", "redis", "spring", "database", "cross"]

# 词权重:品牌/符号术语 2,多词短语 3,普通术语 1;栈得分 ≥2 触发规则路由
KEYWORD_RULES = {
    "k8s": {
        "kubectl": 2, "kubernetes": 2, "k8s": 2, "deployment": 2, "ingress": 2,
        "namespace": 2, "helm": 2, "statefulset": 2, "daemonset": 2,
        "crashloopbackoff": 2, "sidecar": 2, "kubelet": 2, "pod": 1, "pods": 1,
        "configmap": 2, "kubectl apply": 3,
    },
    "kafka": {
        "kafka": 2, "consumer group": 3, "consumer": 1, "producer": 2, "partition": 2,
        "broker": 2, "offset": 2, "zookeeper": 2, "kraft": 2, "rebalance": 2,
        "消费者组": 3, "消费组": 3, "重平衡": 2, "消息队列": 2,
        "session.timeout.ms": 2, "heartbeat.interval.ms": 2, "max.poll": 2,
    },
    "redis": {
        "redis": 2, "keyspace": 2, "sentinel": 2, "redisson": 2, "lettuce": 2,
        "rdb": 1, "aof": 1, "缓存穿透": 3, "缓存雪崩": 3,
    },
    "spring": {
        "spring": 2, "spring boot": 3, "spring cloud": 3, "spring data": 3,
        "@bean": 2, "@autowired": 2, "autowired": 2, "jpa": 2, "transactional": 2,
        "actuator": 2,
    },
    "database": {
        "mysql": 2, "postgresql": 2, "postgres": 1, "oracle": 2,
        "死锁": 2, "慢查询": 3, "连接池": 2, "deadlock": 1, "索引": 1, "explain": 1,
    },
}

_VERSION_PATTERNS = [
    r"(?:kubernetes|k8s)\s*v?(\d+\.\d+(?:\.\d+)?)",
    r"spring\s*boot\s*v?(\d+\.\d+(?:\.\d+)?)",
    r"(?:kafka|redis|mysql|postgres(?:ql)?|spring|java)\s*v?(\d+\.\d+(?:\.\d+)?)",
    r"版本\s*v?(\d+\.\d+(?:\.\d+)?)",
]
_COMPILED_VERSIONS = [re.compile(p) for p in _VERSION_PATTERNS]

_TROUBLESHOOTING_HINTS = ("报错", "错误", "异常", "故障", "排查", "失败", "error", "exception", "timeout", "超时")
_API_HINTS = ("api", "接口", "参数", "签名", "字段")
_GUIDE_HINTS = ("怎么", "如何", "配置", "部署", "安装", "使用", "最佳实践", "指南")

_LLM_SYSTEM = (
    "你是技术栈分类器。判断用户问题涉及哪些技术栈,只输出 JSON:"
    '{"tech_stack": ["k8s"|"kafka"|"redis"|"spring"|"database"|"cross"], "confidence": 0~1}。'
    "无法判断时 tech_stack 为空数组。"
)


@dataclass
class RoutingResult:
    stacks: list
    method: str  # rules | llm | fallback_all
    confidence: float
    version: Optional[str] = None
    doc_type_hint: Optional[str] = None


def extract_version(query: str):
    low = query.lower()
    for pat in _COMPILED_VERSIONS:
        m = pat.search(low)
        if m:
            return m.group(1)
    return None


def extract_doc_type(query: str):
    low = query.lower()
    for hints, doc_type in (
        (_TROUBLESHOOTING_HINTS, "troubleshooting"),
        (_API_HINTS, "api_reference"),
        (_GUIDE_HINTS, "guide"),
    ):
        if any(h in low for h in hints):
            return doc_type
    return None


def _rule_scores(query: str) -> dict:
    low = query.lower()
    scores = {}
    for stack, terms in KEYWORD_RULES.items():
        s = sum(w for term, w in terms.items() if term in low)
        if s:
            scores[stack] = s
    return scores


def _extract_json(raw: str):
    start, end = raw.find("{"), raw.rfind("}")
    if start >= 0 and end > start:
        return raw[start : end + 1]
    return raw


def route(query: str, llm=None) -> RoutingResult:
    version = extract_version(query)
    hint = extract_doc_type(query)
    scores = _rule_scores(query)
    eligible = sorted(
        (s for s, v in scores.items() if v >= 2), key=lambda x: (-scores[x], x)
    )[:2]
    if eligible:
        confidence = min(0.95, 0.55 + 0.08 * scores[eligible[0]])
        return RoutingResult(eligible, "rules", confidence, version, hint)
    if llm is not None:
        try:
            raw = llm.chat(_LLM_SYSTEM, [{"role": "user", "content": query}])
            data = json.loads(_extract_json(raw))
            stacks = [s for s in data.get("tech_stack", []) if s in TECH_STACKS and s != "unknown"]
            confidence = float(data.get("confidence", 0))
            if stacks and confidence >= 0.5:
                return RoutingResult(stacks[:2], "llm", confidence, version, hint)
        except Exception:  # noqa: BLE001
            pass
    return RoutingResult(list(ALL_STACKS), "fallback_all", 0.3, version, hint)
