import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import get_settings
from app.models.user import User
from app.services.auth import create_jwt_token, get_steam_openid_url, verify_steam_openid

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/auth", tags=["Auth"])


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
