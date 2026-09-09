import logging
from typing import Any

import httpx

from app.adapters.base import AdapterConfig, BaseAdapter, TransientError

logger = logging.getLogger(__name__)

PLAYER_SERVICE_URL = "https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/"
WISHLIST_SERVICE_URL = "https://api.steampowered.com/IWishlistService/GetWishlist/v1/"


class PrivateProfileError(Exception):
    """Lỗi bắn ra khi Steam profile bị khoá Private (không lấy được thư viện)."""
    pass


class SteamUserAdapter(BaseAdapter[dict[str, Any], dict[str, Any]]):
    """Adapter lấy dữ liệu người dùng từ Steam (Thư viện & Wishlist)."""

    source = "steam_user"

    def __init__(self, config: AdapterConfig, http: httpx.AsyncClient, api_key: str) -> None:
        super().__init__(config)
        self._http = http
        self._api_key = api_key

    async def fetch_raw(self, **params: Any) -> dict[str, Any]:
        """Tự động định tuyến giữa GetOwnedGames và GetWishlist."""
        steam_id64 = params.get("steam_id64")
        operation = params.get("op", "owned_games")

        if operation == "owned_games":
            try:
                resp = await self._http.get(
                    PLAYER_SERVICE_URL,
                    params={
                        "key": self._api_key,
                        "steamid": steam_id64,
                        "include_appinfo": "true",
                        "include_played_free_games": "true",
                    },
                )
                resp.raise_for_status()
                payload: dict[str, Any] = resp.json()
                return payload
            except httpx.HTTPError as exc:
                raise TransientError(f"Lỗi gọi Steam GetOwnedGames: {exc!r}") from exc

        elif operation == "wishlist":
            try:
                resp = await self._http.get(
                    WISHLIST_SERVICE_URL,
                    params={
                        "key": self._api_key,
                        "steamid": steam_id64,
                    },
                )
                resp.raise_for_status()
                wishlist: dict[str, Any] = resp.json()
                return wishlist
            except httpx.HTTPError as exc:
                raise TransientError(f"Lỗi gọi Steam GetWishlist: {exc!r}") from exc

        raise ValueError(f"Unknown operation: {operation}")

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Chuẩn hóa dữ liệu thô."""
        return raw  # Không cần normalize tổng quát ở đây, xử lý thẳng trên kết quả fetch

    async def get_owned_games(self, steam_id64: str) -> list[dict[str, Any]]:
        """Lấy danh sách game đã sở hữu. Bắn PrivateProfileError nếu profile đóng."""
        data = await self.fetch(steam_id64=steam_id64, op="owned_games")
        response = data.get("response", {})

        # Nếu response trống rỗng, tức là profile đóng.
        # (Nếu public nhưng chưa mua game nào thì có game_count = 0)
        if not response and "game_count" not in response:
            raise PrivateProfileError("Steam profile is private")

        games: list[dict[str, Any]] = response.get("games", [])
        return games

    async def get_wishlist(self, steam_id64: str) -> list[dict[str, Any]]:
        """Lấy wishlist."""
        data = await self.fetch(steam_id64=steam_id64, op="wishlist")
        response = data.get("response", {})

        if not response and "items" not in response:
            # wishlist cũng bị ảnh hưởng bởi game details privacy
            raise PrivateProfileError("Steam profile is private")

        items: list[dict[str, Any]] = response.get("items", [])
        return items
