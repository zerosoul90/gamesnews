import logging
from typing import Any, ClassVar

import httpx

from app.adapters.base import AdapterConfig, BaseAdapter, TransientError

logger = logging.getLogger(__name__)

EPIC_FREE_PROMO_URL = "https://store-site-backend-static-ipv4.ak.epicgames.com/freeGamesPromotions"


class EpicFreeGamesAdapter(BaseAdapter[dict[str, Any], list[dict[str, Any]]]):
    """Lấy danh sách game miễn phí hàng tuần từ Epic Games."""

    source: ClassVar[str] = "epic"

    def __init__(self, config: AdapterConfig, http: httpx.AsyncClient) -> None:
        super().__init__(config)
        self._http = http

    async def fetch_raw(self, **params: Any) -> dict[str, Any]:
        try:
            # Epic promotions endpoint không giới hạn rate limit chặt, không cần key
            response = await self._http.get(EPIC_FREE_PROMO_URL)
            response.raise_for_status()
            payload: dict[str, Any] = response.json()
            return payload
        except httpx.HTTPError as exc:
            raise TransientError(f"Không thể lấy danh sách free games Epic: {exc!r}") from exc

    def normalize(self, raw: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            elements = raw["data"]["Catalog"]["searchStore"]["elements"]
        except KeyError:
            return []

        free_games = []
        for el in elements:
            promotions = el.get("promotions")
            if not promotions:
                continue

            # Chỉ quan tâm đến promotion đang diễn ra
            offers = promotions.get("promotionalOffers", [])
            if not offers:
                continue

            for offer in offers:
                promos = offer.get("promotionalOffers", [])
                for promo in promos:
                    discount = promo.get("discountSetting", {}).get("discountPercentage", 0)
                    if discount == 0:  # Miễn phí 100%
                        end_date = promo.get("endDate")
                        free_games.append(
                            {
                                "title": el.get("title"),
                                "slug": el.get("productSlug") or el.get("urlSlug"),
                                "namespace": el.get("namespace"),
                                "promo_ends_at": end_date,
                            }
                        )
        return free_games

    async def fetch_free_games(self) -> list[dict[str, Any]]:
        """Danh sách game đang miễn phí.

        `BaseAdapter.fetch()` đã gọi `normalize` bên trong rồi, nên bản trước
        gọi thêm một lần nữa lên chính kết quả đã chuẩn hoá — `normalize` nhận
        một dict nhưng bị đưa cho một list, và mọi lần chạy đều hỏng.
        """
        return await self.fetch(endpoint="freeGamesPromotions")
