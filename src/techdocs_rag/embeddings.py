# -*- coding: utf-8 -*-
"""可插拔向量化:哈希(零依赖开发默认)/ OpenAI 兼容(生产,如火山方舟 bge-m3)(设计 §6.3)。"""
from __future__ import annotations

import hashlib
import json
import math
import os
import time
import urllib.request
from collections import Counter

from techdocs_rag.text import tokenize


class Embedder:
    name = "abstract"

    def embed_texts(self, texts: list) -> list:
        raise NotImplementedError


class HashEmbedder(Embedder):
    """确定性哈希词袋向量:开发/测试默认;上线前必须切换多语模型并全量重建(设计 §4.4)。"""

    def __init__(self, dim: int = 512):
        self.dim = dim
        self.name = "hash-%d" % dim

    def embed_texts(self, texts: list) -> list:
        return [self._one(t) for t in texts]

    def _one(self, text: str) -> list:
        vec = [0.0] * self.dim
        tf = Counter(tokenize(text))
        for tok, n in tf.items():
            w = 1.0 + math.log(n)
            self._add(vec, tok, w)
            if tok.isascii() and len(tok) >= 4:
                for i in range(len(tok) - 2):
                    self._add(vec, tok[i : i + 3], 0.5 * w)
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0:
            vec = [x / norm for x in vec]
        return vec

    def _add(self, vec, key: str, weight: float) -> None:
        h = int.from_bytes(hashlib.blake2b(key.encode("utf-8"), digest_size=8).digest(), "big")
        idx = h % self.dim
        sign = 1.0 if (h >> 63) & 1 == 0 else -1.0
        vec[idx] += sign * weight


class OpenAICompatibleEmbedder(Embedder):
    """POST {api_base}/embeddings;批量 16;重试 2 次。"""

    def __init__(self, api_base: str, api_key: str, model: str, timeout: int = 30):
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.name = model

    def embed_texts(self, texts: list) -> list:
        out = []
        for i in range(0, len(texts), 16):
            batch = texts[i : i + 16]
            out.extend(self._request(batch))
        return out

    def _request(self, batch: list) -> list:
        payload = json.dumps({"model": self.model, "input": batch}).encode("utf-8")
        last_err = None
        for attempt in range(3):
            try:
                req = urllib.request.Request(
                    self.api_base + "/embeddings",
                    data=payload,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": "Bearer %s" % self.api_key,
                    },
                )
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                return [item["embedding"] for item in sorted(data["data"], key=lambda x: x["index"])]
            except Exception as e:  # noqa: BLE001
                last_err = e
                time.sleep(0.5 * (attempt + 1))
        raise RuntimeError("embedding 请求失败: %s" % last_err)


def build_embedder(env=None):
    env = env if env is not None else os.environ
    base = env.get("TECHDOCS_EMBEDDING_API_BASE")
    key = env.get("TECHDOCS_EMBEDDING_API_KEY")
    model = env.get("TECHDOCS_EMBEDDING_MODEL")
    if base and key and model:
        return OpenAICompatibleEmbedder(base, key, model)
    return HashEmbedder()
