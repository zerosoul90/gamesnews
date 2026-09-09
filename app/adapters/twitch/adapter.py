import hashlib
import hmac
import logging
from typing import Any

import httpx

from app.adapters.base import PermanentError, TransientError, classify_http_status

logger = logging.getLogger(__name__)

TWITCH_API_URL = "https://api.twitch.tv/helix"
TWITCH_AUTH_URL = "https://id.twitch.tv/oauth2/token"


class TwitchAdapter:
    """Adapter gọi API Twitch và xử lý Webhook (EventSub)"""

    def __init__(
        self,
        http: httpx.AsyncClient,
        client_id: str,
        client_secret: str,
        webhook_secret: str,
    ) -> None:
        # `webhook_secret` cố ý KHÔNG có giá trị mặc định. Một chuỗi mẫu ai
        # cũng đoán được mà lại dùng để ký EventSub thì chữ ký thành vô nghĩa,
        # và tệ hơn là nó vẫn "chạy" nên không ai phát hiện.
        self._http = http
        self._client_id = client_id
        self._client_secret = client_secret
        self._webhook_secret = webhook_secret
        self._access_token: str | None = None

    async def _get_app_access_token(self) -> str:
        """Lấy token App Access từ Twitch"""
        if self._access_token:
            return self._access_token

        if not self._client_id or not self._client_secret:
            raise PermanentError("Thiếu twitch_client_id hoặc twitch_client_secret")

        try:
            response = await self._http.post(
                TWITCH_AUTH_URL,
                data={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "grant_type": "client_credentials",
                },
            )
            response.raise_for_status()
            data = response.json()
            self._access_token = data.get("access_token")
            return self._access_token or ""
        except httpx.HTTPError as exc:
            raise TransientError(f"Không thể lấy token Twitch: {exc!r}") from exc

    async def get_streams(self, user_logins: list[str]) -> list[dict[str, Any]]:
        """Lấy thông tin stream hiện tại của một list streamer"""
        if not user_logins:
            return []

        token = await self._get_app_access_token()
        headers = {
            "Client-ID": self._client_id,
            "Authorization": f"Bearer {token}",
        }

        # Twitch nhận tối đa 100 kênh mỗi request.
        params: list[tuple[str, str | int | float | bool | None]] = [
            ("user_login", login) for login in user_logins[:100]
        ]

        try:
            response = await self._http.get(
                f"{TWITCH_API_URL}/streams",
                headers=headers,
                params=params,
            )
            error = classify_http_status(response.status_code)
            if error is not None:
                raise error(
                    f"Lỗi gọi Twitch Get Streams -> {response.status_code}: {response.text[:200]}"
                )

            data: dict[str, Any] = response.json()
            streams: list[dict[str, Any]] = data.get("data", [])
            return streams
        except httpx.HTTPError as exc:
            raise TransientError(f"Không gọi được Twitch Get Streams: {exc!r}") from exc

    def verify_eventsub_signature(
        self, message_id: str, message_timestamp: str, body: bytes, signature: str
    ) -> bool:
        """
        Xác minh chữ ký HMAC SHA256 của Twitch Webhook EventSub
        """
        message = message_id.encode() + message_timestamp.encode() + body
        expected_hmac = hmac.new(self._webhook_secret.encode(), message, hashlib.sha256).hexdigest()
        expected_signature = f"sha256={expected_hmac}"
        return hmac.compare_digest(expected_signature, signature)
