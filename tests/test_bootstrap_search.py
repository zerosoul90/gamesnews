"""Index Meilisearch phải được dựng lúc khởi động, và `/search` phải nói thật.

`core/bootstrap.py` đã gom mọi `ensure_indexes` của Mongo lại, nhưng index
Meilisearch thì không: nó chỉ được tạo bên trong `reindex()`, mà job đó chưa
chạy lần nào trên một deploy mới. Hậu quả kiểm được bằng cách dựng một stack
sạch — `/health` báo cả bốn kho `ok` (Meilisearch sống, chỉ là chưa có index)
trong khi mọi truy vấn `/search` trả 500 `index_not_found`.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.api.search import INDEX_NOT_READY_DETAIL
from app.core.bootstrap import ensure_storage
from app.core.deps import get_meili
from app.main import app
from app.search.meili import INDEX_NOT_FOUND, MeiliError, MeiliIndex

Db = AsyncIOMotorDatabase[dict[str, Any]]


# --- ensure_storage dựng cả index Meilisearch ------------------------------


async def test_ensure_storage_dung_index_meili(
    mongo_db: Db, meili_index: MeiliIndex
) -> None:
    """`meili_index` xoá index trước khi yield, nên điểm xuất phát đúng bằng
    một deploy trắng: trước bootstrap thì tìm kiếm ném `index_not_found`."""
    with pytest.raises(MeiliError) as chua_dung:
        await meili_index.search("elden ring")
    assert chua_dung.value.code == INDEX_NOT_FOUND

    created = await ensure_storage(mongo_db, meili_index)

    assert created["meili_games"] == 1
    assert (await meili_index.search("elden ring"))["hits"] == []


async def test_ensure_storage_chay_lai_duoc(
    mongo_db: Db, meili_index: MeiliIndex
) -> None:
    """API và worker cùng gọi `ensure_storage` mỗi lần khởi động, nên lượt thứ
    hai không được đỏ.

    Đúng cái bẫy đã ghi trong PROGRESS.md: Meilisearch báo "index đã tồn tại"
    trong *task*, không bằng mã HTTP.
    """
    await ensure_storage(mongo_db, meili_index)
    await ensure_storage(mongo_db, meili_index)

    assert (await meili_index.search(""))["hits"] == []


async def test_ensure_storage_khong_co_meili_van_dung_mongo(mongo_db: Db) -> None:
    """`index` là tuỳ chọn: chỗ nào chỉ cần phần Mongo thì gọi không kèm."""
    created = await ensure_storage(mongo_db)

    assert "meili_games" not in created
    assert created["games"] > 0


# --- /search nói đúng chuyện gì đang xảy ra --------------------------------
#
# Dùng fake thay Meilisearch thật: `TestClient` chạy event loop riêng, còn
# `MeiliIndex` trong fixture giữ một `httpx.AsyncClient` gắn với loop của
# pytest-asyncio. Thứ đang kiểm ở đây là ánh xạ lỗi -> mã HTTP, không phải hành
# vi của Meilisearch.


class FakeIndexRaising:
    def __init__(self, error: MeiliError) -> None:
        self._error = error

    async def search(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        raise self._error


def client_raising(error: MeiliError) -> TestClient:
    app.dependency_overrides[get_meili] = lambda: FakeIndexRaising(error)
    return TestClient(app)


def teardown_function() -> None:
    app.dependency_overrides.clear()


def test_index_chua_dung_tra_503_khong_phai_500() -> None:
    """Index chưa có là hạ tầng chưa sẵn sàng, phải nói đúng như vậy.

    Trước lượt này `MeiliError` không ai bắt và người dùng nhận
    `500 Internal Server Error` kèm traceback — một lỗi lập trình, không phải
    một trạng thái vận hành hiểu được.
    """
    error = MeiliError("POST /indexes/games/search -> 404", code=INDEX_NOT_FOUND)
    response = client_raising(error).get("/search", params={"q": "elden ring"})

    assert response.status_code == 503
    assert response.json()["detail"] == INDEX_NOT_READY_DETAIL


def test_loi_meili_khac_van_noi_len_thanh_500() -> None:
    """Chỉ nuốt đúng `index_not_found`.

    Bắt hết `MeiliError` rồi trả 503 thì một master key sai cũng thành "chưa
    sẵn sàng", và sẽ không có ai đi sửa.
    """
    error = MeiliError("POST /indexes/games/search -> 403", code="invalid_api_key")
    with pytest.raises(MeiliError):
        client_raising(error).get("/search", params={"q": "elden ring"})


def test_loi_khong_co_ma_van_noi_len() -> None:
    """Body không phải JSON của Meilisearch (proxy, tầng mạng) -> `code` là
    None, và None không phải `index_not_found` nên lỗi vẫn nổi lên."""
    with pytest.raises(MeiliError):
        client_raising(MeiliError("502 từ proxy")).get("/search")
