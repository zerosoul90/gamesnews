import logging
from typing import Any

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import get_settings
from app.models.user import User
from app.services.auth import create_jwt_token, get_steam_openid_url, verify_steam_openid

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/auth", tags=["Auth"])
security = HTTPBearer()


# --- dependency xác thực ---------------------------------------------------
#
# Đặt ở đây chứ không ở router nào khác: `api/user.py` và `api/community.py`
# đều cần, mà mỗi nơi tự giải mã JWT một kiểu thì sớm muộn hai nơi lệch nhau
# về thuật toán hoặc về cách xử lý token hết hạn — kiểu lỗi âm thầm mở cửa.


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict[str, Any]:
    """Payload JWT đã xác thực. 401 nếu token sai hoặc hết hạn."""
    settings = get_settings()
    try:
        payload: dict[str, Any] = jwt.decode(
            credentials.credentials,
            settings.jwt_secret.get_secret_value(),
            algorithms=["HS256"],
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=401, detail="Token không hợp lệ hoặc đã hết hạn"
        ) from exc
    return payload


async def get_current_user_id(
    payload: dict[str, Any] = Depends(get_current_user),
) -> str:
    """Chỉ lấy _id của user. `create_jwt_token` đặt nó ở claim `sub`."""
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token thiếu định danh user")
    return str(user_id)


@router.get("/steam/login")
async def steam_login() -> RedirectResponse:
    """Redirect tới trang đăng nhập Steam OpenID."""
    settings = get_settings()
    return_to = f"{settings.frontend_url}/api/v1/auth/steam/callback"
    url = get_steam_openid_url(return_to)
    return RedirectResponse(url)


@router.get("/steam/callback")
async def steam_callback(request: Request) -> dict[str, Any]:
    """Xử lý callback từ Steam, trả về JWT."""
    db: AsyncIOMotorDatabase[dict[str, Any]] = request.app.state.clients.db
    http = request.app.state.clients.http

    query_params = dict(request.query_params)
    steam_id64 = await verify_steam_openid(http, query_params)

    if not steam_id64:
        raise HTTPException(status_code=401, detail="Xác thực Steam thất bại.")

    # Tìm hoặc tạo User
    user_doc = await db.users.find_one({"steam_id64": steam_id64})
    if not user_doc:
        new_user = User(steam_id64=steam_id64)
        result = await db.users.insert_one(new_user.to_mongo())
        user_id = str(result.inserted_id)
    else:
        user_id = str(user_doc["_id"])

    token = create_jwt_token(user_id=user_id, steam_id64=steam_id64)

    return {
        "access_token": token,
        "token_type": "bearer",
        "steam_id64": steam_id64,
        "user_id": user_id,
    }
