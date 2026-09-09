import logging
from typing import Any

import httpx

from app.adapters.base import PermanentError, TransientError, classify_http_status

logger = logging.getLogger(__name__)

STORE_API_URL = "https://store.steampowered.com/api"
WEB_API_URL = "https://api.steampowered.com"


class SteamChartsAdapter:
    """Adapter lấy dữ liệu xếp hạng, CCU và reviews từ Steam."""

    def __init__(self, http: httpx.AsyncClient, api_key: str = "", country: str = "vn") -> None:
        self._http = http
        self._api_key = api_key
        self._country = country

    async def _get_json(self, url: str, params: dict[str, str]) -> Any:
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

    async def get_top_sellers_vn(self) -> list[int]:
        """Top sellers của gian hàng VN. Trả về danh sách appid.

        `getappsincategory?category=topsellers&cc=vn` — endpoint mà
        `PHASE-7.md` nêu — trả `{"status": 1}` **rỗng, không có items** (kiểm
        tay 2026-09-09). Nó không lỗi, chỉ là không còn dữ liệu, nên bản trước
        trả `[]` mãi mà không có gì đỏ lên.

        `featuredcategories` là thứ thay thế duy nhất còn sống, và nó trả giá
        VND thật. Nhược điểm phải biết trước khi tin vào con số này: nó chỉ cho
        **10 mục**, không phải cả bảng xếp hạng. Đủ để bơm vào tầng hot của
        `price_tier` (đó là toàn bộ chỗ đang dùng nó), **không** đủ để dựng một
        trang "bán chạy nhất".
        """
        url = f"{STORE_API_URL}/featuredcategories/"
        params = {"cc": self._country, "l": "english"}
        data = await self._get_json(url, params)

        # Cấu trúc: data["top_sellers"]["items"] = [{"id": 12345}, ...]
        if data.get("status") != 1:
            logger.warning("Steam không trả về status 1 cho featuredcategories")
            return []

        top_sellers_category = data.get("top_sellers", {})
        if not top_sellers_category:
            # Khoá đổi tên thì còn `id` để nhận ra. Không tìm thấy cũng không
            # sao: trả rỗng, tầng hot vẫn còn hai nguồn tín hiệu kia.
            for value in data.values():
                if isinstance(value, dict) and value.get("id") == "cat_topsellers":
                    top_sellers_category = value
                    break

        items = top_sellers_category.get("items", [])
        appids = []
        for item in items:
            appid = item.get("id")
            if appid:
                appids.append(int(appid))
        return appids

    async def get_most_played(self) -> list[dict[str, Any]]:
        """
        Lấy Top CCU (Current Concurrent Users) hiện tại.
        Sử dụng ISteamChartsService/GetGamesByConcurrentPlayers/v1/ (Yêu cầu Web API Key).
        """
        if not self._api_key:
            logger.warning("GetGamesByConcurrentPlayers yêu cầu steam_api_key.")
            return []

        url = f"{WEB_API_URL}/ISteamChartsService/GetGamesByConcurrentPlayers/v1/"
        data = await self._get_json(url, {"key": self._api_key})

        # Cấu trúc:
        # {"response": {"ranks": [
        #     {"rank": 1, "appid": 730, "concurrent_in_game": 1000000}, ...
        # ]}}
        ranks: list[dict[str, Any]] = data.get("response", {}).get("ranks", [])
        return ranks
