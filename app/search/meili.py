"""Index `games` trên Meilisearch — xem `docs/PHASE-1.md` mục 6.

Dùng httpx thẳng, chưa thêm SDK riêng của Meilisearch: phần API cần ở đây rất
nhỏ (settings, documents, search, tasks) và Phase 0 đã có sẵn một
`httpx.AsyncClient` dùng chung vòng đời với app.

Mọi thao tác ghi của Meilisearch đều **bất đồng bộ**: server trả về `taskUid`
rồi mới xử lý sau. Không chờ task xong thì job reindex báo thành công trong khi
index còn rỗng, nên `wait_for_task` là phần bắt buộc chứ không phải tiện ích.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

INDEX_UID = "games"
PRIMARY_KEY = "id"

# Thứ tự có ý nghĩa: Meilisearch xếp hạng theo thuộc tính nào khớp, thuộc tính
# đứng trước thắng. Tên chính thắng alias là điều ta muốn — người gõ đúng tên
# game phải ra game đó trước một game khác chỉ trùng ở alias.
SEARCHABLE_ATTRIBUTES = [
    "titles.primary",
    "titles.vi",
    "aliases_normalized",
    "aliases",
]

FILTERABLE_ATTRIBUTES = ["platforms", "genres", "release_year", "type"]
SORTABLE_ATTRIBUTES = ["release_year"]

# `type_rank:asc` đặt SAU `exactness`, không phải trước.
#
# PHASE-1.md mục 6 muốn game chính xếp trên DLC. Nhưng nếu để trước `exactness`
# thì nó thắng cả độ khớp: tìm đúng tên một DLC vẫn bị game cha đẩy lên đầu.
# Đặt cuối thì nó chỉ phá thế hoà — đúng lúc cần, và chỉ lúc đó.
RANKING_RULES = [
    "words",
    "typo",
    "proximity",
    "attribute",
    "sort",
    "exactness",
    "type_rank:asc",
]

# Số nhỏ xếp trước. Bundle vẫn là sản phẩm chính nên đứng trên demo và DLC.
TYPE_RANK = {"game": 0, "bundle": 1, "demo": 2, "dlc": 3}


# Mã lỗi của Meilisearch. Cần đến chúng để phân biệt "index chưa được dựng"
# với "Meilisearch hỏng thật" — hai chuyện đòi hai cách xử lý khác hẳn nhau.
INDEX_NOT_FOUND = "index_not_found"
INDEX_ALREADY_EXISTS = "index_already_exists"


class MeiliError(RuntimeError):
    """Meilisearch trả lỗi, hoặc một task ghi thất bại.

    `code` là mã lỗi máy đọc được của Meilisearch. Nơi gọi cần phân biệt các
    trường hợp thì so theo nó, đừng dò chuỗi trong message — message có kèm cả
    body cắt ngắn, đổi lúc nào không hay.
    """

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


def _error_code(response: httpx.Response) -> str | None:
    """Lấy `code` trong body lỗi, chịu được body không phải JSON.

    Lỗi từ proxy hay từ tầng mạng không có dạng JSON của Meilisearch; lúc đó
    không có mã nào để trả về và nơi gọi phải coi như lỗi lạ.
    """
    try:
        body = response.json()
    except ValueError:
        return None
    return body.get("code") if isinstance(body, dict) else None


def to_search_document(doc: dict[str, Any]) -> dict[str, Any]:
    """Đổi một document Mongo thành document để index.

    Chỉ mang theo thứ dùng để tìm, lọc hoặc hiển thị trong danh sách kết quả.
    Không đẩy cả system_requirements hay screenshots sang — index phình ra thì
    chậm mà chẳng ai tìm theo chúng.
    """
    release_dates = doc.get("release_dates") or []
    years = [
        int(date[:4])
        for rd in release_dates
        if isinstance(date := rd.get("date"), str) and date[:4].isdigit()
    ]
    game_type = doc.get("type", "game")

    return {
        "id": str(doc["_id"]),
        "slug": doc.get("slug"),
        "titles": doc.get("titles") or {},
        "aliases": doc.get("aliases") or [],
        "aliases_normalized": doc.get("aliases_normalized") or [],
        "platforms": doc.get("platforms") or [],
        "genres": doc.get("genres") or [],
        "type": game_type,
        "type_rank": TYPE_RANK.get(game_type, len(TYPE_RANK)),
        "release_year": min(years) if years else None,
        "cover": (doc.get("media") or {}).get("cover"),
    }


class MeiliIndex:
    """Bọc đúng phần API Meilisearch mà Phase 1 cần."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        base_url: str,
        api_key: str,
        *,
        uid: str = INDEX_UID,
    ) -> None:
        self._http = http
        self._base = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._uid = uid

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        response = await self._http.request(
            method, f"{self._base}{path}", headers=self._headers, **kwargs
        )
        if response.status_code >= 400:
            raise MeiliError(
                f"{method} {path} -> {response.status_code}: {response.text[:300]}",
                code=_error_code(response),
            )
        return response.json() if response.content else None

    async def wait_for_task(
        self,
        task_uid: int,
        *,
        timeout_seconds: float = 60.0,
        ignore_error_codes: frozenset[str] = frozenset(),
    ) -> None:
        """Chờ một task ghi kết thúc. Task hỏng thì ném lỗi kèm nguyên nhân.

        `ignore_error_codes` cho phép coi một số lỗi là kết quả chấp nhận được.
        Cần đến nó vì Meilisearch báo "index không tồn tại" / "index đã tồn tại"
        **trong task**, không phải bằng mã HTTP: xoá một index không có vẫn trả
        202 kèm taskUid, rồi task đó mới failed. Job chạy lại được phải nuốt
        đúng hai trường hợp này.
        """
        deadline = time.monotonic() + timeout_seconds
        delay = 0.02
        while True:
            task = await self._request("GET", f"/tasks/{task_uid}")
            status = task.get("status")
            if status == "succeeded":
                return
            if status == "failed":
                error = task.get("error") or {}
                code = error.get("code")
                if code in ignore_error_codes:
                    return
                raise MeiliError(f"task {task_uid} hỏng: {error}", code=code)
            if time.monotonic() > deadline:
                raise MeiliError(
                    f"task {task_uid} quá {timeout_seconds}s vẫn ở trạng thái {status}"
                )
            await asyncio.sleep(delay)
            delay = min(delay * 2, 0.5)  # backoff nhẹ, đừng dội hàng nghìn lần

    async def ensure_index(self) -> None:
        """Tạo index và áp settings. Chạy lại được.

        Meilisearch trả 409 khi index đã tồn tại — đó là kết quả mong muốn của
        một job chạy lại, không phải lỗi.
        """
        task = await self._request(
            "POST", "/indexes", json={"uid": self._uid, "primaryKey": PRIMARY_KEY}
        )
        await self.wait_for_task(
            task["taskUid"], ignore_error_codes=frozenset({INDEX_ALREADY_EXISTS})
        )

        task = await self._request(
            "PATCH",
            f"/indexes/{self._uid}/settings",
            json={
                "searchableAttributes": SEARCHABLE_ATTRIBUTES,
                "filterableAttributes": FILTERABLE_ATTRIBUTES,
                "sortableAttributes": SORTABLE_ATTRIBUTES,
                "rankingRules": RANKING_RULES,
                "typoTolerance": {"enabled": True},
            },
        )
        await self.wait_for_task(task["taskUid"])

    async def add_documents(self, documents: list[dict[str, Any]]) -> None:
        if not documents:
            return
        task = await self._request(
            "POST", f"/indexes/{self._uid}/documents", json=documents
        )
        await self.wait_for_task(task["taskUid"])

    async def delete_index(self) -> None:
        """Xoá hẳn index. Index không tồn tại thì coi như xong."""
        task = await self._request("DELETE", f"/indexes/{self._uid}")
        await self.wait_for_task(
            task["taskUid"], ignore_error_codes=frozenset({INDEX_NOT_FOUND})
        )

    async def delete_document(self, document_id: str) -> None:
        """Xoá một document khỏi index. Không có sẵn thì task vẫn succeeded.

        Cần cho thao tác gộp entity của trang admin: entity bị gộp phải biến
        mất khỏi kết quả tìm kiếm ngay, chứ không đợi lần reindex toàn bộ kế
        tiếp — trong khoảng chờ đó nó vẫn hiện ra và trỏ tới một _id đã chết.
        """
        task = await self._request("DELETE", f"/indexes/{self._uid}/documents/{document_id}")
        await self.wait_for_task(task["taskUid"])

    async def delete_all_documents(self) -> None:
        task = await self._request("DELETE", f"/indexes/{self._uid}/documents")
        await self.wait_for_task(task["taskUid"])

    async def search(
        self,
        query: str,
        *,
        filters: list[str] | None = None,
        facets: list[str] | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"q": query, "limit": limit, "offset": offset}
        if filters:
            # Danh sách lồng nhau = AND giữa các nhóm, OR trong một nhóm.
            body["filter"] = filters
        if facets:
            body["facets"] = facets
        result = await self._request("POST", f"/indexes/{self._uid}/search", json=body)
        return dict(result)
