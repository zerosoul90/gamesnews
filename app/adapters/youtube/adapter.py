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
