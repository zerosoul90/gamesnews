"""GET /search — `docs/PHASE-1.md` mục 7.

Query, facet filter, phân trang, và trả về cả facet count.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.deps import MeiliDep
from app.search.meili import FILTERABLE_ATTRIBUTES, INDEX_NOT_FOUND, MeiliError

router = APIRouter(tags=["search"])

MAX_PER_PAGE = 50

# Index Meilisearch chưa tồn tại nghĩa là `ensure_storage` chưa dựng được nó —
# hạ tầng chưa sẵn sàng, không phải "catalog rỗng". Trả 200 kèm danh sách rỗng
# ở đây thì một deploy hỏng trông y hệt một deploy chạy đúng nhưng chưa có dữ
# liệu, và sẽ không ai biết để đi sửa.
INDEX_NOT_READY_DETAIL = "index tìm kiếm chưa sẵn sàng"


class SearchHit(BaseModel):
    id: str
    slug: str | None = None
    titles: dict[str, str | None] = Field(default_factory=dict)
    platforms: list[str] = Field(default_factory=list)
    genres: list[str] = Field(default_factory=list)
    type: str = "game"
    release_year: int | None = None
    cover: str | None = None


class SearchResponse(BaseModel):
    query: str
    total: int
    page: int
    per_page: int
    hits: list[SearchHit]
    # {"platforms": {"pc": 120, "ps5": 44}, "release_year": {"2022": 31}, ...}
    facets: dict[str, dict[str, int]] = Field(default_factory=dict)


def _quote(value: str) -> str:
    """Bọc một giá trị thành literal chuỗi trong cú pháp filter Meilisearch.

    Giá trị đến thẳng từ query string nên phải escape: một dấu nháy kép lọt vào
    là đóng sớm literal và phần còn lại bị đọc như cú pháp filter.
    """
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _filter_group(field: str, values: list[str]) -> str | None:
    """Nhiều giá trị cùng một field là OR: platform=pc&platform=ps5 nghĩa là
    'có mặt trên PC **hoặc** PS5'. Giữa các field khác nhau mới là AND."""
    if not values:
        return None
    return " OR ".join(f"{field} = {_quote(value)}" for value in values)


@router.get("/search", response_model=SearchResponse)
async def search(
    index: MeiliDep,
    q: Annotated[str, Query(description="Từ khoá; để trống thì duyệt toàn bộ")] = "",
    platform: Annotated[list[str] | None, Query()] = None,
    genre: Annotated[list[str] | None, Query()] = None,
    year: Annotated[list[int] | None, Query()] = None,
    # Che builtin `type` trong phạm vi hàm này là có chủ ý: tên tham số phải
    # khớp tên field trong SCHEMA.md để URL đọc lên là hiểu.
    type: Annotated[list[str] | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=MAX_PER_PAGE)] = 20,
) -> SearchResponse:
    groups = [
        _filter_group("platforms", platform or []),
        _filter_group("genres", genre or []),
        # release_year là số, không bọc nháy.
        " OR ".join(f"release_year = {value}" for value in year) if year else None,
        _filter_group("type", type or []),
    ]
    filters = [group for group in groups if group]

    try:
        result = await index.search(
            q,
            filters=filters,
            facets=FILTERABLE_ATTRIBUTES,
            limit=per_page,
            offset=(page - 1) * per_page,
        )
    except MeiliError as exc:
        # Chỉ nuốt đúng trường hợp này. Mọi mã lỗi Meilisearch khác vẫn nổi lên
        # thành 500 — bắt hết rồi trả 503 thì một master key sai cũng thành
        # "chưa sẵn sàng" và sẽ không có ai đi sửa.
        if exc.code != INDEX_NOT_FOUND:
            raise
        raise HTTPException(status_code=503, detail=INDEX_NOT_READY_DETAIL) from exc

    raw_facets: dict[str, dict[str, Any]] = result.get("facetDistribution") or {}
    return SearchResponse(
        query=q,
        total=int(result.get("estimatedTotalHits", 0)),
        page=page,
        per_page=per_page,
        hits=[SearchHit.model_validate(hit) for hit in result.get("hits", [])],
        facets={
            field: {str(key): int(count) for key, count in values.items()}
            for field, values in raw_facets.items()
        },
    )
