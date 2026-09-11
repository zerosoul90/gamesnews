"""Điểm đánh giá Steam — `store.steampowered.com/appreviews/<appid>`.

`user_reviews` của ta rỗng (0 bản ghi) và không có giao diện nào để viết review,
nên `community_score` luôn trả `average_score: null`. Đây là nguồn điểm đánh giá
thật duy nhất đang có trong tay.

**Cùng host `store.steampowered.com` với `appdetails`, nên cùng hạn mức tính
theo IP.** Vì vậy job đọc điểm phải dùng CHUNG bucket `steam_appdetails` với job
giá và job catalog — bucket riêng nghĩa là ba job cùng tiêu một hạn mức mà không
ai biết tổng, rồi job giá bị 429 vì một lý do không liên quan tới nó.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

import httpx

from app.adapters.base import (
    AdapterConfig,
    BaseAdapter,
    PermanentError,
    TransientError,
    classify_http_status,
)

logger = logging.getLogger(__name__)

APP_REVIEWS_URL = "https://store.steampowered.com/appreviews/{appid}"


class SteamReviewsAdapter(BaseAdapter[dict[str, Any], dict[str, Any] | None]):
    """Tóm tắt điểm đánh giá của một app. `None` nghĩa là chưa có điểm để nói."""

    source: ClassVar[str] = "steam"

    def __init__(self, config: AdapterConfig, http: httpx.AsyncClient) -> None:
        super().__init__(config)
        self._http = http

    async def fetch_raw(self, **params: Any) -> dict[str, Any]:
        appid = params["appid"]
        try:
            response = await self._http.get(
                APP_REVIEWS_URL.format(appid=appid),
                params={
                    "json": 1,
                    # `language=all`: điểm trên trang store là điểm mọi ngôn ngữ.
                    # Lọc theo một ngôn ngữ ra một con số khác hẳn với con số
                    # người dùng thấy khi bấm sang Steam để đối chiếu.
                    "language": "all",
                    # Gồm cả key/gift, đúng như mặc định của trang store.
                    "purchase_type": "all",
                    # 0 = chỉ lấy `query_summary`, không tải nội dung review nào.
                    # Mặc định là 20 review đầy đủ cho mỗi app — vài chục KB cho
                    # một thứ ta không dùng.
                    "num_per_page": 0,
                },
            )
        except httpx.HTTPError as exc:
            raise TransientError(f"Không gọi được appreviews/{appid}: {exc!r}") from exc

        # `classify_http_status` trả về LỚP lỗi, không phải instance.
        error = classify_http_status(response.status_code)
        if error is not None:
            raise error(f"appreviews/{appid} -> {response.status_code}: {response.text[:200]}")

        try:
            payload: dict[str, Any] = response.json()
        except ValueError as exc:
            raise PermanentError(f"appreviews/{appid} trả về không phải JSON: {exc}") from exc
        return payload

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any] | None:
        """`query_summary` -> dict để ghi xuống, hoặc None khi không có điểm.

        **Steam trả 200 kèm `success: 1` cho cả appid không tồn tại.** Kiểm tay
        2026-09-11 với appid 999999999: payload là
        `{"review_score": 0, "review_score_desc": "No user reviews",
        "total_reviews": 0}` — một summary hợp lệ hoàn hảo. Nên không có cách nào
        phân biệt "appid sai" với "game thật chưa ai đánh giá".

        Hệ quả: `total_reviews == 0` phải trả None, KHÔNG được ghi `score: 0`.
        Ghi 0 thì trang hiện "0/10" và người đọc hiểu là game bị chấm 0 điểm,
        trong khi sự thật là ta không biết gì. Cùng một lỗi với chuyện
        `/api/v1/og-image` từng vẽ giá viết cứng cho mọi game.
        """
        if not raw.get("success"):
            return None

        summary = raw.get("query_summary") or {}
        total = int(summary.get("total_reviews") or 0)
        if total <= 0:
            return None

        positive = int(summary.get("total_positive") or 0)
        negative = int(summary.get("total_negative") or 0)
        if positive + negative != total:
            # Không chặn, nhưng phải biết: `positive_percent` tính trên `total`
            # nên lệch ở đây là lệch luôn con số hiển thị.
            logger.warning(
                "appreviews: positive + negative khác total",
                extra={"positive": positive, "negative": negative, "total": total},
            )

        return {
            # Thang 0-9 của Steam, nhóm rất thô: cả Elden Ring (1,15 triệu
            # review) và một game 84 review đều ra 8 / "Very Positive". Giữ lại
            # vì đó là con số người dùng thấy trên Steam, nhưng không dùng nó làm
            # thứ để so sánh giữa các game.
            "score": int(summary.get("review_score") or 0),
            "score_desc": str(summary.get("review_score_desc") or ""),
            "positive": positive,
            "negative": negative,
            "total": total,
            # Con số thật sự phân biệt được: 93,0% so với 84,5% trong khi cả hai
            # cùng nhãn "Very Positive". Làm tròn 1 chữ số — thêm nữa là giả vờ
            # chính xác trên một đại lượng đổi theo từng giờ.
            "positive_percent": round(positive / total * 100, 1),
        }

    async def fetch_summary(self, appid: int) -> dict[str, Any] | None:
        result: dict[str, Any] | None = await self.fetch(endpoint="appreviews", appid=appid)
        return result
