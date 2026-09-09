import datetime as dt
import urllib.parse

import httpx
import jwt

from app.core.config import get_settings

STEAM_OPENID_URL = "https://steamcommunity.com/openid/login"


def create_jwt_token(user_id: str, steam_id64: str | None = None) -> str:
    """Tạo JWT có hạn 30 ngày."""
    settings = get_settings()
    now = dt.datetime.now(dt.UTC)
    payload = {
        "sub": user_id,
        "steam_id64": steam_id64,
        "iat": int(now.timestamp()),
        "exp": int((now + dt.timedelta(days=30)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm="HS256")


def get_steam_openid_url(return_to: str) -> str:
    """Tạo URL chuyển hướng người dùng sang trang đăng nhập Steam."""
    params = {
        "openid.ns": "http://specs.openid.net/auth/2.0",
        "openid.mode": "checkid_setup",
        "openid.return_to": return_to,
        "openid.realm": urllib.parse.urljoin(return_to, "/"),
        "openid.identity": "http://specs.openid.net/auth/2.0/identifier_select",
        "openid.claimed_id": "http://specs.openid.net/auth/2.0/identifier_select",
    }
    return f"{STEAM_OPENID_URL}?{urllib.parse.urlencode(params)}"


async def verify_steam_openid(http: httpx.AsyncClient, query_params: dict[str, str]) -> str | None:
    """Xác thực payload Steam trả về. Trả về SteamID64 nếu hợp lệ, None nếu không."""
    # Đổi openid.mode thành check_authentication để verify với Steam
    verify_params = dict(query_params)
    verify_params["openid.mode"] = "check_authentication"

    try:
        response = await http.post(STEAM_OPENID_URL, data=verify_params)
        response.raise_for_status()
    except httpx.HTTPError:
        return None

    # Phản hồi có dạng is_valid:true
    if "is_valid:true" not in response.text:
        return None

    claimed_id = query_params.get("openid.claimed_id", "")
    if not claimed_id.startswith("https://steamcommunity.com/openid/id/"):
        return None

    steam_id64 = claimed_id.split("/")[-1]
    if not steam_id64.isdigit():
        return None

    return steam_id64
