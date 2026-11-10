# -*- coding: utf-8 -*-
"""查询预处理:多轮指代改写 + 双语术语扩展(设计 §5.1/§5.2)。"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional

# 中英术语映射:中文提问命中英文官方文档的关键路径
TERM_MAP = {
    "消费者组": "consumer group",
    "消费组": "consumer group",
    "重平衡": "rebalance",
    "死锁": "deadlock",
    "超时": "timeout",
    "连接池": "connection pool",
    "心跳": "heartbeat",
    "持久化": "persistence",
    "事务": "transaction",
    "分区": "partition",
    "索引": "index",
    "慢查询": "slow query",
    "堆栈": "stack trace",
    "重启": "restart",
    "内存溢出": "out of memory",
}

ANAPHORA_MARKERS = ("它", "这个", "该", "上述", "上面", "刚才")

_LLM_SYSTEM = (
    "你是查询改写器。根据对话历史,把用户的追问改写成独立完整的检索查询。"
    "只输出改写后的一句话,不要解释。"
)


@dataclass
class RewrittenQuery:
    original: str
    text: str
    expansions: list = field(default_factory=list)
    method: str = "passthrough"


class QueryRewriter:
    def __init__(self, llm=None, max_history: int = 6):
        self.llm = llm
        self.max_history = max_history

    def rewrite(self, query: str, history: Optional[list] = None) -> RewrittenQuery:
        text = (query or "").strip()
        expansions = []
        method = "passthrough"
        history = history or []
        has_anaphora = any(m in text for m in ANAPHORA_MARKERS)
        short = len(text) <= 6

        if has_anaphora and history:
            prev = next(
                (m.get("content", "") for m in reversed(history) if m.get("role") == "user"), ""
            )
            if prev:
                text = "%s %s" % (prev, text)
                method = "rule_anaphora"
        elif (short or has_anaphora) and history and self.llm is not None:
            try:
                payload = json.dumps(
                    {"history": history[-self.max_history :], "query": query},
                    ensure_ascii=False,
                )
                rewritten = (
                    self.llm.chat(_LLM_SYSTEM, [{"role": "user", "content": payload}])
                    .strip()
                    .splitlines()[0]
                    .strip()
                )
                if rewritten:
                    text = rewritten
                    method = "llm"
            except Exception:  # noqa: BLE001
                pass

        low = text.lower()
        for zh, en in TERM_MAP.items():
            if zh in text and en not in low:
                expansions.append(en)
            elif en in low and zh not in text:
                expansions.append(zh)
        if expansions:
            text = text + " " + " ".join(expansions)
        return RewrittenQuery(original=query, text=text, expansions=expansions, method=method)
