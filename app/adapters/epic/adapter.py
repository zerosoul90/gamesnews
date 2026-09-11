import datetime as dt
import logging
from typing import Any, ClassVar

import httpx

from app.adapters.base import AdapterConfig, BaseAdapter, TransientError

logger = logging.getLogger(__name__)

EPIC_FREE_PROMO_URL = "https://store-site-backend-static-ipv4.ak.epicgames.com/freeGamesPromotions"

# Trang sản phẩm trên store. `pageSlug` của Epic đã gồm hậu tố riêng
# (`luftrausers-51e5e9`), không phải slug ta tự ghép.
EPIC_PRODUCT_URL = "https://store.epicgames.com/p/{slug}"


def _product_slug(element: dict[str, Any]) -> str | None:
    """Slug dùng được để dựng URL trang sản phẩm.

    KHÔNG dùng `productSlug or urlSlug` như bản trước. Kiểm trên payload thật
    2026-09-11: `productSlug` là `None` cho **cả hai** game đang free, còn
    `urlSlug` của Astral Ascent là `d72ccf025e574bb4a725e3079ea34081` — một GUID.
    Lưu GUID đó vào `external_ids.epic_slug` thì field mang tên slug lại chứa
    thứ không tra được, và URL dựng từ nó không dẫn tới đâu.

    `catalogNs.mappings` mới là bảng Epic tự khai, lấy bản ghi `productHome`.
    """
    mappings = (element.get("catalogNs") or {}).get("mappings") or []
    for mapping in mappings:
        if mapping.get("pageType") == "productHome" and (slug := mapping.get("pageSlug")):
            return str(slug)
    return None


def _current_offer(promotions: dict[str, Any], now: dt.datetime) -> dict[str, Any] | None:
    """Đợt khuyến mãi đang diễn ra.

    Chỉ đọc `promotionalOffers`, KHÔNG đọc `upcomingPromotionalOffers`: đợt tuần
    sau chưa có hiệu lực, gắn nó vào `promo_ends_at` là báo cho người dùng một
    hạn chót sai.
    """
    fallback: dict[str, Any] | None = None
    for block in promotions.get("promotionalOffers") or []:
        for raw in block.get("promotionalOffers") or []:
            if not isinstance(raw, dict):
                continue
            offer: dict[str, Any] = raw
            fallback = fallback or offer
            if _within(offer.get("startDate"), offer.get("endDate"), now):
                return offer
    return fallback


def _within(start: Any, end: Any, now: dt.datetime) -> bool:
    try:
        if start and dt.datetime.fromisoformat(str(start).replace("Z", "+00:00")) > now:
            return False
        if end and dt.datetime.fromisoformat(str(end).replace("Z", "+00:00")) <= now:
            return False
    except ValueError:
        # Epic đổi định dạng ngày thì coi như không xác định được cửa sổ, để
        # `_current_offer` rơi về offer đầu tiên thay vì bỏ cả game.
        return False
    return True


class EpicFreeGamesAdapter(BaseAdapter[dict[str, Any], list[dict[str, Any]]]):
    """Game đang miễn phí 100% trên Epic Games Store.

    Chỉ lấy đợt tặng miễn phí, KHÔNG lấy bảng giá Epic nói chung — endpoint này
    chỉ trả nhóm game trong chương trình khuyến mãi.
    """

    source: ClassVar[str] = "epic"

    def __init__(
        self,
        config: AdapterConfig,
        http: httpx.AsyncClient,
        *,
        country: str = "VN",
        locale: str = "vi",
    ) -> None:
        super().__init__(config)
        self._http = http
        self._country = country
        self._locale = locale

    async def fetch_raw(self, **params: Any) -> dict[str, Any]:
        try:
            # `country` quyết định đồng tiền. Không truyền thì Epic trả USD theo
            # cent (`originalPrice: 999`, `decimals: 2`), còn `country=VN` trả
            # `104000` với `decimals: 0` — đúng quy ước số nguyên VND mà
            # `PriceCurrent` và bảng giá Steam đang dùng. Trộn hai thứ vào một
            # cột `price_initial` thì "rẻ nhất" giữa các store thành vô nghĩa.
            response = await self._http.get(
                EPIC_FREE_PROMO_URL, params={"country": self._country, "locale": self._locale}
            )
            response.raise_for_status()
            payload: dict[str, Any] = response.json()
            return payload
        except httpx.HTTPError as exc:
            raise TransientError(f"Không thể lấy danh sách free games Epic: {exc!r}") from exc

    def normalize(self, raw: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            elements = raw["data"]["Catalog"]["searchStore"]["elements"]
        except (KeyError, TypeError):
            return []

        now = dt.datetime.now(dt.UTC)
        free_games = []
        for element in elements:
            promotions = element.get("promotions") or {}
            if not promotions:
                continue

            total = (element.get("price") or {}).get("totalPrice") or {}
            # Điều kiện "miễn phí" đọc từ GIÁ CUỐI, không từ `discountPercentage`.
            # Payload thật 2026-09-11 có 11 element, trong đó Ghostrunner 2,
            # Lost Castle và Monument Valley đều có `promotionalOffers` nhưng chỉ
            # đang giảm giá thường ($7.99, $1.99...). Bản trước đọc
            # `discountSetting.get("discountPercentage", 0)` — mặc định 0 nghĩa
            # là Epic bỏ sót field một lần là cả nhóm giảm giá bị gắn "miễn phí".
            if total.get("discountPrice") != 0:
                continue

            offer = _current_offer(promotions, now)
            if offer is None:
                continue

            slug = _product_slug(element)
            free_games.append(
                {
                    "title": element.get("title"),
                    "slug": slug,
                    "namespace": element.get("namespace"),
                    "promo_ends_at": offer.get("endDate"),
                    "price_initial": total.get("originalPrice"),
                    "currency": total.get("currencyCode"),
                    "url": EPIC_PRODUCT_URL.format(slug=slug) if slug else None,
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
