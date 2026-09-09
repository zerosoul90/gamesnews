import logging
from typing import Any

import httpx

from app.adapters.base import PermanentError, TransientError, classify_http_status

logger = logging.getLogger(__name__)

CHEAPSHARK_API_URL = "https://www.cheapshark.com/api/1.0"

class CheapSharkAdapter:
    """Adapter lấy dữ liệu giá và lịch sử giá thấp nhất từ CheapShark."""

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

    async def search_game(self, title: str) -> list[dict[str, Any]]:
        """
        Tìm kiếm game trên CheapShark bằng tên.
        Trả về list: [{"gameID": "123", "external": "The Witcher 3", "cheapest": "14.99"}]
        """
        url = f"{CHEAPSHARK_API_URL}/games"
        params = {"title": title, "limit": 5}
        data = await self._get_json(url, params=params)

        # CheapShark trả về trực tiếp mảng JSON
        if not isinstance(data, list):
            return []

        results = []
        for item in data:
            results.append({
                "gameID": str(item.get("gameID")),
                "title": item.get("external"),
                "cheapest": float(item.get("cheapest", "0.0")),
                "thumb": item.get("thumb")
            })
        return results

    async def get_historical_low(self, game_id: str) -> dict[str, Any] | None:
        """
        Lấy chi tiết giá thấp nhất lịch sử (Historical Low) của game.
        """
        url = f"{CHEAPSHARK_API_URL}/games"
        params = {"id": game_id}
        data = await self._get_json(url, params=params)

        # Cùng một endpoint `/games` trả về MẢNG khi tra theo `title`, và
        # OBJECT khi tra theo `id`. Gọi `.get` trên mảng thì nổ `AttributeError`
        # — một lỗi lập trình, mà `adapters/base` xếp lỗi lạ vào nhóm vĩnh viễn
        # nên nó sẽ giết cả lô chứ không chỉ một game.
        if not isinstance(data, dict):
            return None

        info = data.get("info") or {}
        cheapest_price_ever = data.get("cheapestPriceEver") or {}

        if not info or not cheapest_price_ever:
            return None

        try:
            price_val = float(cheapest_price_ever.get("price", "0.0"))
            date_val = int(cheapest_price_ever.get("date", 0)) # UNIX timestamp
        except (ValueError, TypeError):
            price_val = 0.0
            date_val = 0

        return {
            "game_id": game_id,
            "title": info.get("title"),
            "lowest_ever_price": price_val,
            "lowest_ever_date": date_val
        }
