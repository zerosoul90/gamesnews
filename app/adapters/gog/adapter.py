"""Adapter GOG — **chưa job nào gọi, và đã đo là KHÔNG nên viết job giá.**

Đo tay 2026-09-11, ghi lại đây để người sau không phải đo lại:

**1. GOG không bán bằng VND.** `currencyCode` có tác dụng thật — xin EUR nhận
EUR, xin PLN nhận PLN — nhưng xin VND thì rơi về USD, kể cả khi kèm
`countryCode=VN`. Nên dữ liệu này không vào được `price_current` (đang là VND đơn
vị lớn); nó phải nằm ở `price_intl` như CheapShark.

**2. Toàn bộ giá trị đã có sẵn qua CheapShark.** CheapShark có GOG trong danh
sách store (storeID 7). Bốn game mà API GOG khớp được — Cyberpunk 2077 $59.99,
Stardew Valley $14.99, Hollow Knight $14.99, Baldur's Gate 3 $59.99 — đều đã có
dòng GOG trong `price_intl` với **giá trùng khít**.

**3. CheapShark không bỏ sót.** 10 game mà CheapShark nói "không có GOG" (Elden
Ring, Dark Souls III, Sekiro, RDR2, Persona 5, NieR: Automata...) — API GOG xác
nhận **0/10** thật sự có trên GOG. Chúng không DRM-free nên GOG không bán.

**4. Khớp theo tên ở đây rủi ro thật.** GOG không có khoá join nào sang Steam:

- `like:NieR Automata` trả về "Star Fleet Deluxe", "Bombshell", "AI War 2" —
  rác hoàn toàn. Lấy kết quả đầu tiên là gắn giá Star Fleet Deluxe cho NieR.
- `like:Half-Life: Opposing Force` trả **HTTP 400** (`["Something went wrong..."]`):
  dấu câu trong tên làm vỡ parser truy vấn của GOG.
- `productType` không dùng để lọc được: Cyberpunk 2077 trên GOG là `pack`, nên
  lọc `== "game"` loại oan chính game gốc.

Kết luận: không viết job giá GOG. Thứ GOG có mà CheapShark không có là
`external_ids.gog_id` — nó cho `entity_matcher.match_by_store_link` nhận ra entity
từ một link GOG trong bài viết, tức tầng 1 của bộ khớp, chắc hơn khớp theo tên.
Nếu sau này cần GOG thì làm đúng phần đó, đừng làm giá.
"""

import logging
from typing import Any

import httpx

from app.adapters.base import PermanentError, TransientError, classify_http_status

logger = logging.getLogger(__name__)

GOG_CATALOG_URL = "https://catalog.gog.com/v1/catalog"

class GogAdapter:
    """Adapter lấy dữ liệu giá và tìm kiếm game từ GOG."""

    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    async def _get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        try:
            response = await self._http.get(url, params=params)
        except httpx.HTTPError as exc:
            raise TransientError(f"Không gọi được {url}: {exc!r}") from exc

        error = classify_http_status(response.status_code)
        if error is not None:
            raise error(f"{url} -> {response.status_code}: {response.text[:200]}")
        try:
            return response.json()
        except ValueError as exc:
            raise PermanentError(f"{url} trả về không phải JSON: {exc}") from exc

    async def search_game_by_title(self, title: str) -> list[dict[str, Any]]:
        """
        Tìm game trên GOG theo tiêu đề.
        """
        params = {
            "query": f"like:{title}",
            "limit": 5,
            "order": "desc:relevance"
        }
        data = await self._get_json(GOG_CATALOG_URL, params=params)

        results = []
        products = data.get("products", [])
        for p in products:
            results.append({
                "id": str(p.get("id")), # GOG id thường là số
                "title": p.get("title"),
                "slug": p.get("slug")
            })
        return results

    async def get_price(self, gog_id: str, currency: str = "USD") -> dict[str, Any] | None:
        """Giá hiện tại của một game trên GOG.

        Mặc định là **USD, không phải VND**. Bản trước mặc định `"VND"`, và đó là
        một cái bẫy: GOG nhận tham số nhưng lặng lẽ trả USD cho VND (xem docstring
        của module), nên người gọi tin vào mặc định sẽ lưu số đô vào một cột đang
        chứa đồng. Trường `currency` trả về đọc từ chính response, nên nó luôn nói
        thật — nhưng tên tham số thì đừng hứa điều API không làm.
        """
        params = {
            "id": gog_id,
            "currencyCode": currency
        }
        data = await self._get_json(GOG_CATALOG_URL, params=params)
        products = data.get("products", [])

        if not products:
            return None

        product = products[0]
        price_info = product.get("price", {})

        final_price = price_info.get("finalMoney", {}).get("amount", "0")
        initial_price = price_info.get("baseMoney", {}).get("amount", "0")
        discount_percent = 0

        try:
            final_val = float(final_price)
            initial_val = float(initial_price)
            if initial_val > 0:
                discount_percent = round((1 - final_val / initial_val) * 100)
        except (ValueError, TypeError):
            final_val = 0.0
            initial_val = 0.0

        return {
            "gog_id": gog_id,
            "price_final": final_val,
            "price_initial": initial_val,
            "discount_percent": discount_percent,
            "currency": price_info.get("finalMoney", {}).get("currency", currency)
        }
