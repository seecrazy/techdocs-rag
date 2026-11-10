# -*- coding: utf-8 -*-
"""API 测试(FastAPI TestClient,设计 §11)。"""
from __future__ import annotations

from fastapi.testclient import TestClient

from techdocs_rag.api.app import create_app


def _client(qa):
    service = qa()
    return TestClient(create_app(qa_service=service, pipeline=service.ingestion))


class TestHealth:
    def test_health(self, qa):
        resp = _client(qa).get("/api/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert "collections" in body


class TestQuery:
    def test_query_e2e(self, qa):
        client = _client(qa)
        resp = client.post(
            "/api/query",
            json={"question": "kafka consumer group rebalance 触发条件", "permissions": ["public", "internal"]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["refused"] is False
        assert any(c["source_id"] == "kafka/consumer.md" for c in body["citations"])
        assert body["trace_id"]

    def test_query_refused(self, qa):
        client = _client(qa)
        resp = client.post("/api/query", json={"question": "今天天气怎么样", "permissions": ["public"]})
        assert resp.status_code == 200
        assert resp.json()["refused"] is True

    def test_multiturn_session(self, qa):
        client = _client(qa)
        r1 = client.post("/api/query", json={"question": "Kafka 消费者组 session.timeout.ms 是什么", "session_id": "api-s1", "permissions": ["public"]})
        r2 = client.post("/api/query", json={"question": "那它的默认值是多少?", "session_id": "api-s1", "permissions": ["public"]})
        assert r2.status_code == 200
        assert "kafka/consumer.md" in r2.json()["answer"]


class TestFeedback:
    def test_feedback_recorded(self, qa):
        client = _client(qa)
        q = client.post("/api/query", json={"question": "kafka consumer group 配置", "permissions": ["public"]}).json()
        resp = client.post("/api/feedback", json={"trace_id": q["trace_id"], "helpful": False, "comment": "答非所问"})
        assert resp.status_code == 200


class TestIngest:
    def test_ingest_endpoint(self, qa):
        client = _client(qa)
        resp = client.post("/api/ingest", json={"path": str(qa().docs_root)})
        assert resp.status_code == 200
        body = resp.json()
        assert body["failed"] == 0
        # 夹具已入库过:幂等重跑应为全零;stats 中应有 collection
        assert client.get("/api/health").json()["collections"]
