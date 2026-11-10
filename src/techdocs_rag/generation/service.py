# -*- coding: utf-8 -*-
"""QAService:改写→路由→混合检索→注入处置→重排→拒答→父块扩展→生成→引用校验(设计 §1/§7)。"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone

from techdocs_rag.generation.citation import validate_and_clean
from techdocs_rag.generation.llm import MockLLM
from techdocs_rag.generation.prompt import SYSTEM_PROMPT, assemble_context, build_messages
from techdocs_rag.models import AnswerResult
from techdocs_rag.retrieval.filters import RetrievalFilters
from techdocs_rag.retrieval.hybrid import hybrid_search
from techdocs_rag.retrieval.reranker import NoopReranker
from techdocs_rag.retrieval.router import route
from techdocs_rag.retrieval.rewriter import QueryRewriter

REFUSAL_ANSWER = (
    "未在知识库中找到足够相关的内容。建议:①换一种表述重新提问;"
    "②检查是否涉及尚未收录的技术栈。"
)

_MAX_HISTORY = 6
_MAX_TURN_CHARS = 500


class QAService:
    def __init__(
        self,
        index_store,
        doc_store,
        embedder,
        llm=None,
        reranker=None,
        router_llm=None,
        rewriter=None,
        config=None,
        trace_store=None,
        session_store=None,
    ):
        self.index_store = index_store
        self.doc_store = doc_store
        self.embedder = embedder
        self.llm = llm or MockLLM()
        self.reranker = reranker or NoopReranker()
        self.router_llm = router_llm
        self.rewriter = rewriter or QueryRewriter()
        self.config = config
        self.trace_store = trace_store
        self.session_store = session_store  # 提供 load_session/append_turn 即持久化多轮
        self.sessions = {}

    def ask(
        self,
        question: str,
        session_id: str = None,
        permissions=None,
        version: str = None,
    ) -> AnswerResult:
        cfg = self.config
        perms = set(permissions) if permissions else {"public"}
        trace_id = uuid.uuid4().hex
        trace = {
            "trace_id": trace_id,
            "ts": datetime.now(timezone.utc).isoformat(),
            "session_id": session_id,
            "question": question,
        }

        # 1. 查询预处理:多轮改写 + 双语术语扩展(设计 §5)
        history = self._history(session_id)
        rq = self.rewriter.rewrite(question, history)
        trace["rewritten"] = rq.text
        trace["rewrite_method"] = rq.method

        # 2. 路由:技术栈 + 版本 + doc_type 意图(设计 §6.1)
        routing = route(rq.text, llm=self.router_llm)
        effective_version = version or routing.version
        trace["routing"] = {
            "stacks": routing.stacks,
            "method": routing.method,
            "confidence": routing.confidence,
            "version": effective_version,
            "doc_type_hint": routing.doc_type_hint,
        }

        # 3. 混合检索 + 通道内权限/版本过滤 + 注入排除(设计 §6.2/§6.5/§6.6/§8.1)
        filters = RetrievalFilters(
            permissions=perms,
            version=effective_version,
            version_policy=cfg.retrieval.version_policy,
            doc_type_hint=routing.doc_type_hint,
            exclude_external_suspect=cfg.security.injection_exclude_external,
        )
        family_latest = self.doc_store.latest_family_versions()
        query_vec = self.embedder.embed_texts([rq.text])[0]
        candidates, relevance = [], 0.0
        for stack in routing.stacks:
            collection = "collection_" + stack
            results, rel = hybrid_search(
                self.index_store, collection, rq.text, query_vec, filters,
                cfg.retrieval, family_latest,
            )
            candidates.extend(results)
            relevance = max(relevance, rel)
        trace["retrieval"] = {
            "relevance": round(relevance, 4),
            "candidates": len(candidates),
        }

        # 4. 重排(设计 §6.6)
        candidates = self.reranker.rerank(rq.text, candidates)
        trace["rerank_top"] = [
            {"id": r.chunk.id, "score": round(r.rerank_score, 4) if r.rerank_score is not None else None}
            for r in candidates[:10]
        ]

        # 5. 拒答:候选为空或 relevance 低于校准阈值,不调用 LLM(设计 §6.7)
        refused = False
        answer, citations, warning, context_chunks = REFUSAL_ANSWER, [], "", []
        if cfg.refusal.enabled and (not candidates or relevance < cfg.refusal.min_top_score):
            refused = True
            trace["refusal"] = {
                "decision": True,
                "relevance": round(relevance, 4),
                "threshold": cfg.refusal.min_top_score,
            }
        else:
            context_chunks = self._context(candidates[: cfg.retrieval.final_top_k])
            context_str = assemble_context(context_chunks, cfg.retrieval.max_context_tokens)
            messages = build_messages(question, context_str, history)
            started = time.time()
            answer = self.llm.chat(SYSTEM_PROMPT, messages)
            trace["llm"] = {
                "model": self.llm.name,
                "latency_ms": int((time.time() - started) * 1000),
            }
            # 6. 引用运行期校验(设计 §7.3)
            allowed = {c.metadata.source_id for c in context_chunks}
            answer, citations, n_invalid = validate_and_clean(answer, allowed)
            trace["citations_invalid"] = n_invalid
            trace["no_valid_citation"] = not refused and not citations
            if n_invalid:
                warning = "%d 处引用未通过校验,已移除" % n_invalid
            if session_id:
                self._remember(session_id, question, answer)

        trace["context_chunk_ids"] = [c.id for c in context_chunks]
        trace["answer_snippet"] = answer[:200]
        trace["refused"] = refused
        if self.trace_store is not None:
            self.trace_store.append(trace)
        return AnswerResult(
            answer=answer,
            refused=refused,
            citations=citations,
            routing=trace["routing"],
            context_chunk_ids=trace["context_chunk_ids"],
            context_source_ids=[c.metadata.source_id for c in context_chunks],
            warning=warning,
            trace_id=trace_id,
            relevance=round(relevance, 4),
        )

    # -- 内部 -------------------------------------------------------------

    def _context(self, top: list) -> list:
        """Top-k → 父块扩展 + 去重(设计 §3.3)。"""
        chunks, seen = [], set()
        for r in top:
            m = r.chunk.metadata
            target = r.chunk
            if m.parent_id and self.config.retrieval.expand_parent:
                collection = "collection_" + m.tech_stack
                parent = self.index_store.get_chunks(collection, [m.parent_id]).get(m.parent_id)
                if parent is not None:
                    target = parent
            if target.id in seen:
                continue
            seen.add(target.id)
            chunks.append(target)
        return chunks

    def _history(self, session_id):
        if not session_id:
            return []
        if self.session_store is not None:
            return self.session_store.load_session(session_id, _MAX_HISTORY)
        return self.sessions.get(session_id, [])

    def _remember(self, session_id: str, question: str, answer: str) -> None:
        turns = self.sessions.setdefault(session_id, [])
        turns.append({"role": "user", "content": question[:_MAX_TURN_CHARS]})
        turns.append({"role": "assistant", "content": answer[:_MAX_TURN_CHARS]})
        del turns[:-_MAX_HISTORY]
        if self.session_store is not None:
            self.session_store.append_turn(session_id, "user", question)
            self.session_store.append_turn(session_id, "assistant", answer)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
