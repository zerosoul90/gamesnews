"""Giá nhiều store từ CheapShark — `https://www.cheapshark.com/api/1.0`.

Tới lượt này `price_current` chỉ có `steam` (VND) và `epic` (đợt tặng miễn phí),
nên bảng so sánh giá trên trang game gần như luôn một dòng. CheapShark gom giá
của 35 store, và quan trọng hơn: response của nó mang sẵn `steamAppID`, tức join
thẳng vào catalog của ta **không cần khớp mờ theo tên**.

Ba thứ đo tay 2026-09-11, cả ba đều là chỗ dễ hỏng im lặng:

1. **Bắt buộc User-Agent mô tả được.** Thiếu là `400` kèm
   `"Missing or generic User-Agent header detected"`. Bản adapter trước không đặt
   header nào, nên mọi lời gọi của nó đều 400 — may là chưa job nào gọi.
2. **`steamAppID` KHÔNG nhận nhiều giá trị.** `steamAppID=a,b,c` trả `200` kèm
   đúng **một** kết quả, không báo lỗi. Dùng nó như tham số lô là lặng lẽ mất
   dữ liệu.
3. **`ids` nhận lô nhưng cắt ở 25.** Gửi 26 trả `200` kèm đúng 25. Cùng lớp bẫy
   với trần 50 appid của `price_overview` bên Steam.

Giá CheapShark là **USD, không có tham số đổi quốc gia**. Nên dữ liệu này KHÔNG
vào `price_current`: collection đó đang là VND đơn vị lớn, mà `/deals` lại không
lọc region — một dòng USD lọt vào đó sẽ được trang deal hiển thị "51.59" thành
"52₫". Xem `app/services/intl_prices.py`.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.adapters.base import PermanentError, TransientError, classify_http_status

logger = logging.getLogger(__name__)

CHEAPSHARK_API_URL = "https://www.cheapshark.com/api/1.0"

# CheapShark đòi UA nhận dạng được client. Để kèm URL repo đúng như ví dụ trong
# thông báo lỗi của họ, để nếu ta gọi sai thì họ liên hệ được.
USER_AGENT = "GameNews/0.1 (+https://github.com/zerosoul90/gamesnews)"

# Trần thật của tham số `ids`, đo tay: gửi 26 nhận về 25, không có lỗi nào.
IDS_BATCH = 25

# Link đi mua. CheapShark chuyển hướng sang store kèm theo dõi affiliate của họ;
# `dealID` trong payload đã được URL-encode sẵn.
REDIRECT_URL = "https://www.cheapshark.com/redirect?dealID={deal_id}"


def _cents(value: Any) -> int | None:
    """Chuỗi USD -> số cent.

    Giữ số nguyên cent thay vì float: tiền mà để float thì 51.59 thành
    51.589999999999996, rồi con số đó đi thẳng vào giao diện. Tên field ở chỗ lưu
    cũng mang chữ `cents` để không ai đọc nhầm thang đo.
    """
    if value is None:
        return None
    try:
        return round(float(value) * 100)
    except (TypeError, ValueError):
        return None


class CheapSharkAdapter:
    """Giá nhiều store và đáy lịch sử từ CheapShark."""

    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    async def _get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{CHEAPSHARK_API_URL}{path}"
        try:
            response = await self._http.get(url, params=params, headers={"User-Agent": USER_AGENT})
        except httpx.HTTPError as exc:
            raise TransientError(f"Không gọi được {url}: {exc!r}") from exc

        error = classify_http_status(response.status_code)
        if error is not None:
            raise error(f"{url} -> {response.status_code}: {response.text[:200]}")
        try:
            return response.json()
        except ValueError as exc:
            raise PermanentError(f"{url} trả về không phải JSON: {exc}") from exc

    async def stores(self) -> dict[str, str]:
        """Bảng `storeID` -> tên store.

        Payload giá chỉ mang `storeID` dạng chuỗi số, nên không có bảng này thì
        giao diện hiện "store 23" thay vì "GreenManGaming".
        """
        data = await self._get_json("/stores")
        if not isinstance(data, list):
            return {}
        return {
            str(row["storeID"]): str(row.get("storeName") or "")
            for row in data
            if isinstance(row, dict) and row.get("storeID") is not None
        }

    async def search_game(self, title: str, *, limit: int = 5) -> list[dict[str, Any]]:
        """Tra `gameID` theo tên.

        Đường dự phòng cho game KHÔNG có `steam_appid` — catalog còn entity tới từ
        App Store và Google Play, và với chúng thì `game_id_for_steam_appid` không
        dùng được. Khớp theo tên nên kém chắc hơn hẳn: payload thật cho
        "Batman Arkham Knight" trả về cả bản Season Pass và Premium Edition, nên
        người gọi phải tự quyết chứ đừng lấy kết quả đầu tiên.

        `cheapest` trả về dạng **cent**, cùng thang với `prices_for_game_ids`.
        """
        data = await self._get_json("/games", {"title": title, "limit": limit})
        if not isinstance(data, list):
            return []
        return [
            {
                "game_id": str(row["gameID"]),
                "title": row.get("external"),
                # Có thể là None: bản Season Pass / Premium không gắn appid Steam.
                "steam_appid": int(row["steamAppID"]) if row.get("steamAppID") else None,
                "cheapest_cents": _cents(row.get("cheapest")),
                "thumb": row.get("thumb"),
            }
            for row in data
            if isinstance(row, dict) and row.get("gameID") is not None
        ]

    async def game_id_for_steam_appid(self, steam_appid: int) -> str | None:
        """`gameID` của CheapShark cho một appid Steam.

        Một request một appid: tham số `steamAppID` không nhận danh sách (xem
        docstring của module). Kết quả nên được lưu vào
        `external_ids.cheapshark_id` để lượt sau khỏi hỏi lại.
        """
        data = await self._get_json("/games", {"steamAppID": str(steam_appid)})
        if not isinstance(data, list):
            return None
        for row in data:
            if isinstance(row, dict) and row.get("gameID") is not None:
                return str(row["gameID"])
        return None

    async def prices_for_game_ids(self, game_ids: list[str]) -> dict[str, dict[str, Any]]:
        """Giá từng store cho một lô `gameID`, tối đa `IDS_BATCH` mỗi lần.

        Chặn quá trần ngay tại đây thay vì tin người gọi: gửi quá là mất dữ liệu
        mà không có lỗi nào nổi lên.
        """
        if not game_ids:
            return {}
        if len(game_ids) > IDS_BATCH:
            raise PermanentError(
                f"xin {len(game_ids)} gameID nhưng `ids` của CheapShark cắt ở {IDS_BATCH}"
            )

        data = await self._get_json("/games", {"ids": ",".join(game_ids)})
        if not isinstance(data, dict):
            return {}

        out: dict[str, dict[str, Any]] = {}
        for game_id, payload in data.items():
            if not isinstance(payload, dict):
                continue
            normalized = self._normalize_game(payload)
            if normalized is not None:
                out[str(game_id)] = normalized
        return out

    def _normalize_game(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        # Khai kiểu tường minh: để suy luận thì dict literal trộn int/str/None ra
        # `dict[str, object]`, và `sort(key=...)` dưới đây không còn so được.
        deals: list[dict[str, Any]] = []
        for deal in payload.get("deals") or []:
            if not isinstance(deal, dict):
                continue
            price = _cents(deal.get("price"))
            if price is None:
                continue
            deal_id = deal.get("dealID")
            deals.append(
                {
                    "store_id": str(deal.get("storeID") or ""),
                    "price_cents": price,
                    "retail_price_cents": _cents(deal.get("retailPrice")),
                    # `savings` của CheapShark là phần trăm dạng chuỗi dài
                    # ("14.002334"). Làm tròn: hai chữ số sau dấu phẩy của một
                    # con số phần trăm không mang thêm thông tin nào.
                    "savings_percent": round(float(deal["savings"])) if deal.get("savings") else 0,
                    "url": REDIRECT_URL.format(deal_id=deal_id) if deal_id else None,
                }
            )

        if not deals:
            # Game có trong CheapShark nhưng không store nào bán — không có gì để
            # nói, và ghi một bản ghi rỗng thì trang hiện bảng trống.
            return None

        # Rẻ nhất lên đầu: trang hỏi "mua ở đâu rẻ nhất", nên thứ tự là một phần
        # của câu trả lời. Cùng một đồng tiền nên so số là đúng ở đây.
        deals.sort(key=lambda row: row["price_cents"])

        ever = payload.get("cheapestPriceEver") or {}
        info = payload.get("info") or {}
        return {
            "title": info.get("title"),
            "steam_appid": info.get("steamAppID"),
            "currency": "USD",
            "deals": deals,
            "lowest_ever_cents": _cents(ever.get("price")),
            # UNIX timestamp của CheapShark, giây.
            "lowest_ever_at": int(ever["date"]) if str(ever.get("date") or "").isdigit() else None,
        }
