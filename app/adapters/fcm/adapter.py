"""Firebase Cloud Messaging — HTTP v1.

Thay cho bản mock chỉ ghi một dòng log rồi coi như đã gửi. Kiểu mock đó nguy
hiểm hơn hẳn một stub báo lỗi: mọi tầng phía trên đều tin là thông báo đã tới
tay người dùng, nên không có gì hỏng, không có gì để lần.

## Vì sao phải là HTTP v1, không phải API legacy

Endpoint legacy `fcm.googleapis.com/fcm/send` xác thực bằng một "server key"
dán thẳng vào header — Google đã ngừng nó. Bản v1 xác thực bằng OAuth2 với
**service account**: ta tự ký một JWT assertion bằng khoá riêng, đổi lấy access
token, rồi mới gửi được. Vì vậy dự án phải thêm `pyjwt[crypto]` — HS256 không
ký được assertion này.

## Token của thiết bị sẽ chết, và phải dọn

FCM trả `UNREGISTERED` hoặc `INVALID_ARGUMENT` khi token không còn dùng được
(người dùng gỡ app, cài lại, đổi máy). Không dọn thì danh sách token phình mãi
và mỗi lần gửi lại tốn một request cho một thiết bị không tồn tại. Adapter vì
vậy phân biệt rõ "gửi hỏng tạm thời" với "token này chết hẳn" — xem
`SendResult`.
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass
from typing import Any

import httpx
import jwt

from app.adapters.base import PermanentError, TransientError, classify_http_status

logger = logging.getLogger(__name__)

TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105 - URL, không phải secret
SEND_URL = "https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"
SCOPE = "https://www.googleapis.com/auth/firebase.messaging"

# Access token của Google sống 1 giờ. Xin lại sớm hơn hạn một chút để không có
# khoảng trống giữa lúc hết hạn và lúc xin được cái mới.
TOKEN_TTL = dt.timedelta(minutes=55)

# Mã lỗi nghĩa là token thiết bị chết hẳn, phải xoá khỏi database.
DEAD_TOKEN_CODES = frozenset({"UNREGISTERED", "INVALID_ARGUMENT", "NOT_FOUND"})


@dataclass(frozen=True, slots=True)
class SendResult:
    """Kết quả gửi tới MỘT thiết bị.

    `token_is_dead` tách bạch với `ok=False`: mạng chập chờn thì thử lại lần
    sau, còn token chết thì thử lại bao nhiêu cũng vô ích và phải xoá đi.
    """

    ok: bool
    token_is_dead: bool = False
    error: str | None = None


class FcmAdapter:
    """Gửi push qua FCM HTTP v1 bằng service account."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        project_id: str,
        client_email: str,
        private_key: str,
    ) -> None:
        self._http = http
        self._project_id = project_id
        self._client_email = client_email
        # Khoá trong JSON service account dùng "\n" theo nghĩa đen khi đi qua
        # biến môi trường. Không hoàn nguyên thì PyJWT báo khoá sai định dạng.
        self._private_key = private_key.replace("\\n", "\n")
        self._token: str | None = None
        self._token_expires: dt.datetime | None = None

    @property
    def configured(self) -> bool:
        return bool(self._project_id and self._client_email and self._private_key)

    async def _access_token(self) -> str:
        """Access token còn hạn, xin mới khi cần.

        Cache lại vì mỗi lần xin là một request thật tới Google; gửi thông báo
        cho 500 người mà xin 500 lần token thì phần lớn thời gian là chờ OAuth.
        """
        now = dt.datetime.now(dt.UTC)
        if self._token and self._token_expires and now < self._token_expires:
            return self._token

        assertion = jwt.encode(
            {
                "iss": self._client_email,
                "scope": SCOPE,
                "aud": TOKEN_URL,
                "iat": int(now.timestamp()),
                "exp": int((now + dt.timedelta(hours=1)).timestamp()),
            },
            self._private_key,
            algorithm="RS256",
        )

        try:
            response = await self._http.post(
                TOKEN_URL,
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                    "assertion": assertion,
                },
            )
        except httpx.HTTPError as exc:
            raise TransientError(f"không xin được token FCM: {exc!r}") from exc

        error = classify_http_status(response.status_code)
        if error is not None:
            # Khoá sai hoặc service account bị thu hồi là lỗi vĩnh viễn; retry
            # chỉ làm chậm mọi thứ mà không cứu được gì.
            raise error(f"xin token FCM lỗi {response.status_code}: {response.text[:200]}")

        payload = response.json()
        token = payload.get("access_token")
        if not token:
            raise PermanentError("phản hồi OAuth không có access_token")

        self._token = str(token)
        self._token_expires = now + TOKEN_TTL
        return self._token

    async def send(
        self,
        device_token: str,
        *,
        title: str,
        body: str,
        data: dict[str, Any] | None = None,
    ) -> SendResult:
        """Gửi tới một thiết bị. Không ném lỗi cho trường hợp token chết.

        Người gọi cần phân biệt được ba kết cục để xử lý khác nhau, nên chúng
        được trả về chứ không ném ra: gửi được, token chết (xoá đi), hỏng tạm
        thời (thử lại sau).
        """
        access_token = await self._access_token()
        message: dict[str, Any] = {
            "message": {
                "token": device_token,
                "notification": {"title": title, "body": body},
            }
        }
        if data:
            # FCM chỉ nhận chuỗi trong `data`; số hay bool lọt vào là 400 cho
            # cả tin nhắn.
            message["message"]["data"] = {k: str(v) for k, v in data.items()}

        try:
            response = await self._http.post(
                SEND_URL.format(project_id=self._project_id),
                json=message,
                headers={"Authorization": f"Bearer {access_token}"},
            )
        except httpx.HTTPError as exc:
            return SendResult(ok=False, error=repr(exc))

        if response.status_code < 400:
            return SendResult(ok=True)

        detail = response.json().get("error", {}) if response.content else {}
        status = str(detail.get("status") or "")
        dead = status in DEAD_TOKEN_CODES or response.status_code == 404
        return SendResult(
            ok=False,
            token_is_dead=dead,
            error=f"{response.status_code} {status}"[:200],
        )
