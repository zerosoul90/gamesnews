"""Trang admin entity — `docs/PHASE-1.md` mục 8.

Hai mặt của cùng một nghiệp vụ:

- `/admin/api/...` trả JSON, dùng cho script và cho test.
- `/admin/...` là trang HTML tối giản, server-render bằng Jinja2. Phase 4 mới
  tới Angular; kéo cả một SPA vào đây chỉ để sửa alias là vượt phạm vi Phase 1.

Mọi thao tác ghi đều đẩy thay đổi sang Meilisearch ngay trong request. Chờ job
reindex delta thì admin sửa xong tìm lại vẫn thấy dữ liệu cũ và sẽ sửa lần nữa.
"""

from __future__ import annotations

import pathlib
import secrets
from typing import Annotated, Any

from bson import ObjectId
from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, Response, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from app.core.deps import MeiliDep, MongoDep, SettingsDep
from app.search.meili import MeiliIndex
from app.services import admin as service
from app.services.admin import EntityNotFoundError, MergeConflictError
from app.services.search_index import drop_game, sync_game

TEMPLATE_DIR = pathlib.Path(__file__).resolve().parent.parent / "templates"
TEMPLATES = Jinja2Templates(directory=str(TEMPLATE_DIR))

router = APIRouter(tags=["admin"])

# Token nằm trong cookie chứ không phải query string: query string đi vào log
# của mọi proxy trên đường và vào lịch sử trình duyệt.
COOKIE_NAME = "admin_token"
HEADER_NAME = "X-Admin-Token"

DEFAULT_PER_PAGE = 20
MAX_PER_PAGE = 100


# --- xác thực --------------------------------------------------------------


def _expected_token(settings: SettingsDep) -> str:
    token = settings.admin_token.get_secret_value()
    if not token:
        # Mặc định là ĐÓNG. Một trang sửa được cả catalog mà không có mật khẩu
        # còn tệ hơn nhiều so với việc admin tạm thời không vào được.
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ADMIN_TOKEN chưa được cấu hình nên /admin đang đóng",
        )
    return token


def _supplied_token(request: Request) -> str:
    return request.headers.get(HEADER_NAME) or request.cookies.get(COOKIE_NAME) or ""


def _matches(request: Request, expected: str) -> bool:
    # compare_digest chứ không phải ==: so sánh chuỗi thường thoát ra sớm ở ký
    # tự đầu tiên khác nhau, đủ để đoán dần token qua thời gian phản hồi.
    return secrets.compare_digest(_supplied_token(request), expected)


def require_admin(request: Request, settings: SettingsDep) -> None:
    """Chốt cho nhánh JSON: sai token là 401, không chuyển hướng."""
    if not _matches(request, _expected_token(settings)):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="token admin không đúng")


def require_admin_page(request: Request, settings: SettingsDep) -> None:
    """Chốt cho nhánh HTML: chưa đăng nhập thì đưa về trang đăng nhập.

    Trả 401 cho trình duyệt thì người dùng nhìn thấy một trang lỗi trống và
    không biết phải làm gì tiếp.
    """
    if not _matches(request, _expected_token(settings)):
        raise HTTPException(
            status.HTTP_303_SEE_OTHER,
            detail="chưa đăng nhập",
            headers={"Location": "/admin/login"},
        )


AdminAuth = Depends(require_admin)
PageAuth = Depends(require_admin_page)


def admin_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Đổi lỗi nghiệp vụ thành 4xx. Đăng ký ở `app/main.py`.

    Không có nó thì `MergeConflictError` — một câu trả lời hợp lệ, nghĩa là "hai
    entity này có vẻ không phải một game" — lại hiện ra dưới dạng 500.
    """
    codes = {
        EntityNotFoundError: status.HTTP_404_NOT_FOUND,
        MergeConflictError: status.HTTP_409_CONFLICT,
    }
    return JSONResponse(
        status_code=codes.get(type(exc), status.HTTP_400_BAD_REQUEST),
        content={"detail": str(exc)},
    )


# --- JSON ------------------------------------------------------------------


class AliasUpdate(BaseModel):
    aliases: list[str] = Field(default_factory=list)


class MergeRequest(BaseModel):
    keep_id: str
    drop_id: str


def _public(doc: dict[str, Any]) -> dict[str, Any]:
    """Document Mongo -> JSON.

    Trả nguyên document, kể cả `content_hash`, `updated_at`, `merged_from`:
    người ngồi trang admin cần đúng những field siêu dữ liệu đó để chẩn đoán
    vì sao một entity không lên index hay từ đâu ra.
    """
    encoded: dict[str, Any] = jsonable_encoder(doc, custom_encoder={ObjectId: str})
    return encoded


async def _reindex_one(db: MongoDep, index: MeiliIndex, game_id: ObjectId) -> None:
    await sync_game(db, index, game_id)


@router.get("/admin/api/games", dependencies=[AdminAuth])
async def api_search(
    db: MongoDep,
    q: Annotated[str, Query(description="Tên, slug, hoặc ID ngoài")] = "",
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=MAX_PER_PAGE)] = DEFAULT_PER_PAGE,
) -> dict[str, Any]:
    docs, total = await service.search_entities(
        db, q, limit=per_page, offset=(page - 1) * per_page
    )
    return {
        "query": q,
        "total": total,
        "page": page,
        "per_page": per_page,
        "items": [_public(doc) for doc in docs],
    }


@router.get("/admin/api/games/{game_id}", dependencies=[AdminAuth])
async def api_detail(db: MongoDep, game_id: str) -> dict[str, Any]:
    return _public(await service.get_entity(db, service.to_object_id(game_id)))


@router.put("/admin/api/games/{game_id}/aliases", dependencies=[AdminAuth])
async def api_set_aliases(
    db: MongoDep,
    index: MeiliDep,
    game_id: str,
    payload: AliasUpdate,
) -> dict[str, Any]:
    object_id = service.to_object_id(game_id)
    doc = await service.set_manual_aliases(db, object_id, payload.aliases)
    await _reindex_one(db, index, object_id)
    return _public(doc)


@router.post("/admin/api/games/merge", dependencies=[AdminAuth])
async def api_merge(db: MongoDep, index: MeiliDep, payload: MergeRequest) -> dict[str, Any]:
    keep_id = service.to_object_id(payload.keep_id)
    drop_id = service.to_object_id(payload.drop_id)

    doc = await service.merge_games(db, keep_id=keep_id, drop_id=drop_id)

    # Xoá bên bị gộp khỏi index trước: trong khoảng giữa hai lệnh, thà thiếu
    # một kết quả còn hơn trả về một entity đã không còn trong Mongo.
    await drop_game(index, drop_id)
    await _reindex_one(db, index, keep_id)
    return _public(doc)


# --- HTML ------------------------------------------------------------------


@router.get("/admin/login", response_class=HTMLResponse)
async def login_form(request: Request, settings: SettingsDep) -> Response:
    _expected_token(settings)  # chưa cấu hình token thì báo 503 ngay ở đây
    return TEMPLATES.TemplateResponse(request, "admin/login.html", {"error": None})


@router.post("/admin/login")
async def login(
    request: Request,
    settings: SettingsDep,
    token: Annotated[str, Form()],
) -> Response:
    if not secrets.compare_digest(token, _expected_token(settings)):
        return TEMPLATES.TemplateResponse(
            request,
            "admin/login.html",
            {"error": "Token không đúng."},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    response = RedirectResponse("/admin", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        COOKIE_NAME,
        token,
        httponly=True,  # JS không đọc được -> một lỗi XSS không lấy được token
        samesite="strict",  # chặn form từ site khác POST vào /admin
        secure=settings.app_env != "dev",  # dev chạy http, prod bắt buộc https
        max_age=8 * 3600,
    )
    return response


@router.post("/admin/logout")
async def logout() -> Response:
    response = RedirectResponse("/admin/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(COOKIE_NAME)
    return response


@router.get("/admin", response_class=HTMLResponse, dependencies=[PageAuth])
async def page_list(
    request: Request,
    db: MongoDep,
    q: str = "",
    page: Annotated[int, Query(ge=1)] = 1,
) -> Response:
    docs, total = await service.search_entities(
        db, q, limit=DEFAULT_PER_PAGE, offset=(page - 1) * DEFAULT_PER_PAGE
    )
    return TEMPLATES.TemplateResponse(
        request,
        "admin/list.html",
        {
            "q": q,
            "total": total,
            "page": page,
            "per_page": DEFAULT_PER_PAGE,
            "items": docs,
            "has_next": page * DEFAULT_PER_PAGE < total,
        },
    )


@router.get("/admin/games/{game_id}", response_class=HTMLResponse, dependencies=[PageAuth])
async def page_detail(
    request: Request,
    db: MongoDep,
    game_id: str,
    merged: str = "",
) -> Response:
    doc = await service.get_entity(db, service.to_object_id(game_id))
    return TEMPLATES.TemplateResponse(
        request,
        "admin/detail.html",
        {"game": doc, "merged": merged},
    )


@router.post("/admin/games/{game_id}/aliases", dependencies=[PageAuth])
async def page_set_aliases(
    db: MongoDep,
    index: MeiliDep,
    game_id: str,
    aliases: Annotated[str, Form()] = "",
) -> Response:
    object_id = service.to_object_id(game_id)
    # Ô textarea: mỗi dòng một alias. Dấu phẩy nằm trong tên game thật
    # ("Sonic Frontiers: Final Horizon"), xuống dòng thì không.
    await service.set_manual_aliases(db, object_id, aliases.splitlines())
    await _reindex_one(db, index, object_id)
    return RedirectResponse(f"/admin/games/{game_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/admin/games/{game_id}/merge", dependencies=[PageAuth])
async def page_merge(
    db: MongoDep,
    index: MeiliDep,
    game_id: str,
    drop_id: Annotated[str, Form()],
) -> Response:
    keep = service.to_object_id(game_id)
    drop = service.to_object_id(drop_id)

    await service.merge_games(db, keep_id=keep, drop_id=drop)
    await drop_game(index, drop)
    await _reindex_one(db, index, keep)

    return RedirectResponse(
        f"/admin/games/{game_id}?merged={drop_id}", status_code=status.HTTP_303_SEE_OTHER
    )
