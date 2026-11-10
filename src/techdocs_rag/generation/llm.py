# -*- coding: utf-8 -*-
"""LLM 客户端:OpenAI 兼容(生产,如火山方舟)/ Mock(零依赖开发与测试)(设计 §11)。"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from abc import ABC, abstractmethod


class LLMClient(ABC):
    name = "abstract"

    @abstractmethod
    def chat(self, system: str, messages: list, **kw) -> str:
        raise NotImplementedError


class OpenAICompatibleLLMClient(LLMClient):
    """POST {api_base}/chat/completions;重试 2 次。"""

    def __init__(self, api_base: str, api_key: str, model: str, timeout: int = 60):
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.name = model

    def chat(self, system: str, messages: list, temperature: float = 0.2, **kw) -> str:
        payload = json.dumps(
            {
                "model": self.model,
                "messages": [{"role": "system", "content": system}] + list(messages),
                "temperature": temperature,
                **kw,
            }
        ).encode("utf-8")
        last_err = None
        for attempt in range(3):
            try:
                req = urllib.request.Request(
                    self.api_base + "/chat/completions",
                    data=payload,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": "Bearer %s" % self.api_key,
                    },
                )
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                return data["choices"][0]["message"]["content"]
            except Exception as e:  # noqa: BLE001
                last_err = e
                time.sleep(0.5 * (attempt + 1))
        raise RuntimeError("LLM 请求失败: %s" % last_err)


def _default_mock_handler(system: str, messages: list) -> str:
    """从上下文片段生成带引用的摘要回答,引用必然来自注入片段(可被校验)。"""
    user = messages[-1].get("content", "") if messages else ""
    blocks = re.findall(r"<<<参考片段 \d+>>>\n(.*?)<<<片段结束>>>", user, re.S)
    if not blocks:
        return "根据提供的文档,未找到相关内容。"
    lines = ["根据文档:"]
    for block in blocks[:5]:
        src = re.search(r"来源[:：]\s*(\S+)", block)
        stack = re.search(r"技术栈[:：]\s*(\S+)", block)
        sec = re.search(r"章节[:：]\s*([^|\n]+)", block)
        ver = re.search(r"版本[:：]\s*(\S+)", block)
        body = block.split("<<<内容>>>", 1)
        snippet = body[1].strip().replace("\n", " ")[:80] if len(body) > 1 else ""
        src_id = src.group(1) if src else "unknown"
        section = sec.group(1).strip() if sec else "-"
        lines.append(
            "- [%s] %s:%s… [来源: %s, 章节: %s, 版本: %s]"
            % (
                stack.group(1) if stack else "-",
                section,
                snippet,
                src_id,
                section,
                (ver.group(1) if ver else "unknown"),
            )
        )
    return "\n".join(lines)


class MockLLM(LLMClient):
    name = "mock"

    def __init__(self, handler=None):
        self.handler = handler or _default_mock_handler

    def chat(self, system: str, messages: list, **kw) -> str:
        return self.handler(system, messages)


def build_llm(env=None):
    env = env if env is not None else os.environ
    base = env.get("TECHDOCS_LLM_API_BASE")
    key = env.get("TECHDOCS_LLM_API_KEY")
    model = env.get("TECHDOCS_LLM_MODEL")
    if base and key and model:
        return OpenAICompatibleLLMClient(base, key, model)
    return MockLLM()
