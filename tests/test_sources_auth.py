"""Khoá `/admin/api/sources` — `app/api/sources.py`.

Router này nằm dưới tiền tố `/admin/api/...` nên nhìn qua tưởng được
`api/admin.py` bảo vệ. Nó không: FastAPI **không** thừa kế dependency theo
đường dẫn, và `sources_router` được đăng ký riêng, không có `AdminAuth` nào.

Hậu quả: ai cũng `POST /admin/api/sources` thêm được một feed RSS, và feed đó
chảy thẳng vào đường crawl → LLM → hiển thị công khai. Test này giữ chốt.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import app

TOKEN = "token-admin-cho-test"  # noqa: S105 - token giả dùng trong test


@pytest.fixture
def client() -> Iterator[TestClient]:
    app.dependency_overrides[get_settings] = lambda: Settings(admin_token=TOKEN)
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_khong_token_thi_401(client: TestClient) -> None:
    assert client.get("/admin/api/sources").status_code == 401


def test_token_sai_thi_401(client: TestClient) -> None:
    response = client.post(
        "/admin/api/sources",
        json={"name": "Nguon la", "url": "https://xau.example/rss"},
        headers={"X-Admin-Token": "doan-bua"},
    )
    assert response.status_code == 401


def test_khong_token_thi_khong_them_duoc_nguon(client: TestClient) -> None:
    """Chốt thật: chặn ghi, không chỉ chặn đọc."""
    response = client.post(
        "/admin/api/sources", json={"name": "Nguon la", "url": "https://xau.example/rss"}
    )
    assert response.status_code == 401


def test_patch_status_cung_bi_khoa(client: TestClient) -> None:
    response = client.patch("/admin/api/sources/000000000000000000000000/status?status=inactive")
    assert response.status_code == 401
