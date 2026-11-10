# -*- coding: utf-8 -*-
"""HTTP API(设计 §11):查询 / 入库 / 反馈 / 健康检查。"""
from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from techdocs_rag.connectors.local_file import LocalFileConnector


class QueryRequest(BaseModel):
    question: str
    session_id: Optional[str] = None
    permissions: list = ["public"]
    version: Optional[str] = None


class FeedbackRequest(BaseModel):
    trace_id: str
    helpful: bool
    comment: str = ""


class IngestRequest(BaseModel):
    path: str


def create_app(qa_service, pipeline, config=None) -> FastAPI:
    app = FastAPI(title="TechDocs RAG", version="0.1.0")

    @app.get("/api/health")
    def health():
        return {"status": "ok", "collections": qa_service.index_store.stats()}

    @app.post("/api/query")
    def query(req: QueryRequest):
        if not req.question.strip():
            raise HTTPException(status_code=400, detail="question 不能为空")
        result = qa_service.ask(
            req.question,
            session_id=req.session_id,
            permissions=set(req.permissions),
            version=req.version,
        )
        return {
            "answer": result.answer,
            "refused": result.refused,
            "citations": [
                {"source_id": c.source_id, "section": c.section, "valid": c.valid}
                for c in result.citations
            ],
            "routing": result.routing,
            "context_source_ids": result.context_source_ids,
            "warning": result.warning,
            "trace_id": result.trace_id,
            "relevance": result.relevance,
        }

    @app.post("/api/feedback")
    def feedback(req: FeedbackRequest):
        if qa_service.trace_store is not None:
            qa_service.trace_store.record_feedback(req.trace_id, req.helpful, req.comment)
        return {"ok": True}

    @app.post("/api/ingest")
    def ingest(req: IngestRequest):
        try:
            connector = LocalFileConnector(req.path)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=400, detail="路径不可用: %s" % e)
        report = pipeline.sync(connector)
        return report.as_dict()

    @app.get("/api/stats")
    def stats():
        return {
            "collections": qa_service.index_store.stats(),
            "recent_syncs": qa_service.doc_store.recent_syncs(limit=5),
        }

    return app
