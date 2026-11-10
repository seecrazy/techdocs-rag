# -*- coding: utf-8 -*-
"""配置加载:默认值 + YAML 覆盖(设计 §3.1 切分参数、§6 检索参数)。"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


@dataclass
class ChunkSizeConfig:
    max_tokens: int
    parent_max_tokens: int
    overlap: int


# 设计 §3.1:子块大小 / 父块大小 / 重叠
CHUNKING_DEFAULTS = {
    "api_reference": ChunkSizeConfig(512, 1024, 50),
    "guide": ChunkSizeConfig(1024, 1536, 100),
    "troubleshooting": ChunkSizeConfig(512, 1024, 0),
    "changelog": ChunkSizeConfig(512, 1024, 0),
    "code_example": ChunkSizeConfig(2048, 2048, 0),
    "table": ChunkSizeConfig(1024, 1024, 0),
    "other": ChunkSizeConfig(600, 1024, 80),
}


@dataclass
class RetrievalConfig:
    vector_top_k: int = 15
    bm25_top_k: int = 15
    rrf_k: int = 60
    final_top_k: int = 5
    max_context_tokens: int = 4000
    version_policy: str = "latest"  # latest | all
    expand_parent: bool = True
    fanout_top_k: int = 3


@dataclass
class RefusalConfig:
    enabled: bool = True
    # 初始值,上线前用评估集校准(设计 §6.7)
    min_top_score: float = 0.30


@dataclass
class SecurityConfig:
    injection_exclude_external: bool = True


@dataclass
class AppConfig:
    data_dir: str = ".techdocs_data"
    traces_dir: str = "traces"
    chunking: dict = field(default_factory=lambda: dict(CHUNKING_DEFAULTS))
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    refusal: RefusalConfig = field(default_factory=RefusalConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)


def load_config(path=None) -> AppConfig:
    cfg = AppConfig()
    if path is None:
        path = os.environ.get("TECHDOCS_CONFIG")
    if not path or not os.path.exists(path):
        return cfg
    if yaml is None:  # pragma: no cover
        raise RuntimeError("pyyaml 未安装,无法读取配置文件 %s" % path)
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    for key, value in (raw.get("chunking") or {}).items():
        if key in cfg.chunking and isinstance(value, dict):
            base = cfg.chunking[key]
            cfg.chunking[key] = ChunkSizeConfig(
                max_tokens=value.get("max_tokens", base.max_tokens),
                parent_max_tokens=value.get("parent_max_tokens", base.parent_max_tokens),
                overlap=value.get("overlap", base.overlap),
            )
    for section, target in (
        ("retrieval", cfg.retrieval),
        ("refusal", cfg.refusal),
        ("security", cfg.security),
    ):
        for key, value in (raw.get(section) or {}).items():
            if hasattr(target, key):
                setattr(target, key, value)
    if raw.get("data_dir"):
        cfg.data_dir = raw["data_dir"]
    if raw.get("traces_dir"):
        cfg.traces_dir = raw["traces_dir"]
    return cfg
