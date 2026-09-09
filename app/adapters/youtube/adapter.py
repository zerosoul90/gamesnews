import logging
from typing import Any

import httpx

from app.adapters.base import TransientError, classify_http_status

logger = logging.getLogger(__name__)

YOUTUBE_API_URL = "https://www.googleapis.com/youtube/v3"
PUBSUB_HUB_URL = "https://pubsubhubbub.appspot.com/subscribe"

class YouTubeAdapter:
    """Adapter gọi API YouTube Data V3 và đăng ký WebSub"""

    def __init__(self, http: httpx.AsyncClient, api_key: str) -> None:
        self._http = http
        self._api_key = api_key

    async def get_live_stream(self, channel_id: str) -> dict[str, Any] | None:
        """
        Kiểm tra xem channel có đang live không bằng /search API.
        Lưu ý: /search tốn quota rất lớn (100 point), dùng cẩn thận.
        """
        if not self._api_key:
            return None

        params = {
            "part": "snippet",
            "channelId": channel_id,
            "eventType": "live",
            "type": "video",
            "key": self._api_key,
        }

        try:
            response = await self._http.get(f"{YOUTUBE_API_URL}/search", params=params)
            error = classify_http_status(response.status_code)
            if error is not None:
                raise error(f"Lỗi YouTube API -> {response.status_code}: {response.text[:200]}")

            data = response.json()
            items = data.get("items", [])
            if not items:
                return None
            first: dict[str, Any] = items[0]
            return first
        except httpx.HTTPError as exc:
            raise TransientError(f"Không gọi được YouTube API: {exc!r}") from exc

    async def is_video_live(self, video_id: str) -> bool | None:
        """Video này có đang phát trực tiếp không? None nghĩa là không biết được.

        Vì sao cần: thân notification WebSub của YouTube **giống hệt nhau** cho
        một video mới đăng và một buổi live vừa mở — cùng schema Atom, không có
        trường nào phân biệt. Đẩy push "đang live" cho mọi notification nghĩa là
        mỗi lần streamer đăng một clip cắt là toàn bộ người theo dõi bị đánh
        thức.

        `videos.list` tốn **1 unit** (so với 100 của `search`), tức là quota
        10.000/ngày đủ cho 10.000 notification — nhiều hơn hẳn mức một danh
        sách kênh curate tay có thể sinh ra.
        """
        if not self._api_key:
            return None

        params = {
            "part": "snippet",
            "id": video_id,
            "key": self._api_key,
        }
        try:
            response = await self._http.get(f"{YOUTUBE_API_URL}/videos", params=params)
            error = classify_http_status(response.status_code)
            if error is not None:
                raise error(f"Lỗi YouTube API -> {response.status_code}: {response.text[:200]}")
            items = response.json().get("items", [])
        except httpx.HTTPError as exc:
            raise TransientError(f"Không gọi được YouTube API: {exc!r}") from exc

        if not items:
            # Video vừa bị xoá, hoặc để riêng tư. Không biết được, và cũng
            # không có gì để báo.
            return None
        # "live" = đang phát, "upcoming" = đã lên lịch, "none" = video thường.
        return bool(items[0].get("snippet", {}).get("liveBroadcastContent") == "live")

    async def subscribe_websub(self, channel_id: str, callback_url: str) -> bool:
        """
        Đăng ký WebSub cho kênh YouTube để nhận Webhook khi có video mới / live.
        """
        topic_url = f"https://www.youtube.com/xml/feeds/videos.xml?channel_id={channel_id}"

        data = {
            "hub.callback": callback_url,
            "hub.topic": topic_url,
            "hub.verify": "async",
            "hub.mode": "subscribe",
        }

        try:
            response = await self._http.post(PUBSUB_HUB_URL, data=data)
            # Response 202 Accepted là thành công (async)
            if response.status_code in (202, 204):
                return True
            logger.error(f"YouTube WebSub Error: {response.status_code} {response.text}")
            return False
        except httpx.HTTPError as exc:
            logger.error(f"YouTube WebSub Network Error: {exc!r}")
            return False
