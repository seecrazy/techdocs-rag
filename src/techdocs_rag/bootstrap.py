# -*- coding: utf-8 -*-
"""组件装配:配置 + 环境变量 → 全套上下文(设计 §11)。"""
from __future__ import annotations

import os
from dataclasses import dataclass

from techdocs_rag.config import load_config
from techdocs_rag.connectors.local_file import LocalFileConnector
from techdocs_rag.embeddings import build_embedder
from techdocs_rag.generation.llm import build_llm
from techdocs_rag.generation.service import QAService
from techdocs_rag.ingestion.chunker import StructureAwareChunker
from techdocs_rag.ingestion.pipeline import IngestionPipeline
from techdocs_rag.observability.trace import TraceStore
from techdocs_rag.retrieval.reranker import CrossEncoderReranker, LLMReranker, NoopReranker
from techdocs_rag.retrieval.rewriter import QueryRewriter
from techdocs_rag.storage.chunkstore import SQLiteChunkStore
from techdocs_rag.storage.docstore import DocStore
from techdocs_rag.storage.indexstore import IndexStore


@dataclass
class Context:
    config: object
    chunk_store: object
    index_store: object
    doc_store: object
    trace_store: object
    embedder: object
    llm: object
    reranker: object
    pipeline: object
    service: object

    def local_connector(self, path, rules=None):
        return LocalFileConnector(path, rules=rules)


def build_context(config_path=None, data_dir=None, env=None) -> Context:
    cfg = load_config(config_path)
    env = os.environ if env is None else env
    if data_dir:
        cfg.data_dir = data_dir
    os.makedirs(cfg.data_dir, exist_ok=True)
    os.makedirs(cfg.traces_dir, exist_ok=True)

    chunk_store = SQLiteChunkStore(os.path.join(cfg.data_dir, "chunks.db"))
    doc_store = DocStore(os.path.join(cfg.data_dir, "docs.db"))
    index_store = IndexStore(chunk_store)
    trace_store = TraceStore(cfg.traces_dir)

    llm = build_llm(env)
    embedder = build_embedder(env)
    real_llm = llm.name not in ("mock", "abstract")

    mode = env.get("TECHDOCS_RERANKER", "noop")
    if mode == "cross_encoder":
        reranker = CrossEncoderReranker()
    elif mode == "llm":
        reranker = LLMReranker(llm=llm)
    else:
        reranker = NoopReranker()

    router_llm = llm if real_llm else None
    pipeline = IngestionPipeline(
        index_store=index_store,
        doc_store=doc_store,
        chunker=StructureAwareChunker(cfg.chunking),
        embedder=embedder,
        config=cfg,
    )
    service = QAService(
        index_store=index_store,
        doc_store=doc_store,
        embedder=embedder,
        llm=llm,
        reranker=reranker,
        router_llm=router_llm,
        rewriter=QueryRewriter(llm=router_llm),
        config=cfg,
        trace_store=trace_store,
        session_store=doc_store,
    )
    return Context(
        config=cfg,
        chunk_store=chunk_store,
        index_store=index_store,
        doc_store=doc_store,
        trace_store=trace_store,
        embedder=embedder,
        llm=llm,
        reranker=reranker,
        pipeline=pipeline,
        service=service,
    )
