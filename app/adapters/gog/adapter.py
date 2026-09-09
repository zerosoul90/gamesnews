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

    async def get_price(self, gog_id: str, currency: str = "VND") -> dict[str, Any] | None:
        """
        Lấy thông tin giá hiện tại của game trên GOG.
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
