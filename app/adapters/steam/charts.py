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
        """
        Lấy Top Sellers từ Store API với cc=vn.
        API không chính thức nhưng được dùng rộng rãi:
        /api/getappsincategory/?category=topsellers&cc=vn
        Trả về danh sách appid.
        """
        url = f"{STORE_API_URL}/getappsincategory/"
        params = {"category": "topsellers", "cc": self._country, "l": "english"}
        data = await self._get_json(url, params)

        # Cấu trúc: {"status": 1, "topsellers": {"items": [{"id": 12345}, ...]}}
        if data.get("status") != 1:
            logger.warning("Steam không trả về status 1 cho topsellers")
            return []

        items = data.get("topsellers", {}).get("items", [])
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
