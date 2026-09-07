"""Test /health ở mức đơn vị: kho nào hỏng thì trả mã gì.

Không thay thế được checkpoint `docker compose up` trong PHASE-0 — đó là test
tích hợp thật. Ở đây chỉ khoá lại quy tắc "chỉ phụ thuộc bắt buộc mới đổi mã
HTTP", để sau này sửa nhầm là đỏ ngay.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from app.core.deps import get_clients
from app.main import app


class FakePing:
    def __init__(self, ok: bool) -> None:
        self.ok = ok

    async def __call__(self, *args: Any, **kwargs: Any) -> str:
        if not self.ok:
            raise ConnectionError("kho không phản hồi")
        return "ok"


class FakeClients:
    """Đủ hình dạng để /health gọi được: mongo.admin.command, redis.ping, http.get."""

    def __init__(self, *, mongo: bool, redis: bool, meili: bool, qdrant: bool) -> None:
        self.mongo = type("M", (), {"admin": type("A", (), {"command": FakePing(mongo)})()})()
        self.redis = type("R", (), {"ping": FakePing(redis)})()
        self._meili = FakePing(meili)
        self._qdrant = FakePing(qdrant)
        self.http = type("H", (), {"get": self._get})()

    async def _get(self, url: str, *args: Any, **kwargs: Any) -> str:
        return await (self._qdrant if "6333" in url else self._meili)(url)


def client_with(**flags: bool) -> TestClient:
    app.dependency_overrides[get_clients] = lambda: FakeClients(**flags)
    return TestClient(app)


def teardown_function() -> None:
    app.dependency_overrides.clear()


def test_tat_ca_xanh() -> None:
    with client_with(mongo=True, redis=True, meili=True, qdrant=True) as c:
        response = c.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert {name: check["status"] for name, check in body["checks"].items()} == {
        "mongo": "ok",
        "redis": "ok",
        "meilisearch": "ok",
        "qdrant": "ok",
    }


def test_qdrant_hong_van_200_va_bao_degraded() -> None:
    """Qdrant chưa dùng tới Phase 6 nên không được làm API bị coi là chết."""
    with client_with(mongo=True, redis=True, meili=True, qdrant=False) as c:
        response = c.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["checks"]["qdrant"]["status"] == "down"
    assert body["checks"]["qdrant"]["required"] is False


def test_meilisearch_hong_thi_503() -> None:
    with client_with(mongo=True, redis=True, meili=False, qdrant=True) as c:
        response = c.get("/health")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unhealthy"
    assert body["checks"]["meilisearch"]["required"] is True
    # Chỉ đúng service hỏng bị đánh dấu, các kho khác vẫn xanh.
    assert body["checks"]["mongo"]["status"] == "ok"


def test_mongo_hong_thi_503() -> None:
    with client_with(mongo=False, redis=True, meili=True, qdrant=True) as c:
        response = c.get("/health")

    assert response.status_code == 503
    assert response.json()["checks"]["mongo"]["status"] == "down"


def test_co_request_id_trong_header() -> None:
    with client_with(mongo=True, redis=True, meili=True, qdrant=True) as c:
        response = c.get("/health")
        echoed = c.get("/health", headers={"X-Request-ID": "abc123"})

    assert response.headers["X-Request-ID"]
    # Có id sẵn từ proxy thì giữ nguyên để lần được chuỗi gọi.
    assert echoed.headers["X-Request-ID"] == "abc123"
