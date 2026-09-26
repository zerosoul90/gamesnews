"""Diễn đàn — `docs/FORUM.md`.

Đọc công khai; mọi đường ghi đi qua `_poster()`: JWT → cổng beta → biệt danh.
Chặn tần suất gọi SAU khi request đã hợp lệ, để lỗi của người dùng không đốt
lượt của chính họ.
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Any, Literal

from bson import ObjectId
from fastapi import APIRouter, Depends, Form, Query, Request, Response, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field, field_validator, model_validator

from app.api.admin import TEMPLATES, AdminAuth, PageAuth
from app.api.auth import get_current_user_id, get_optional_user_id
from app.core.deps import ClientsDep, MongoDep, SettingsDep
from app.core.serialization import jsonify as jsonable
from app.services import forum
from app.services.forum import POSTS_PER_PAGE, THREADS_PER_PAGE, ForumError

router = APIRouter(prefix="/api/v1/forum", tags=["forum"])

TITLE_MIN, TITLE_MAX = 5, 150
BODY_MAX = 10_000
REASON_MAX = 500

UserId = Annotated[str, Depends(get_current_user_id)]


def forum_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Đăng ký ở `app/main.py`. Mã trạng thái nằm sẵn trên lớp lỗi."""
    headers = {}
    if not isinstance(exc, ForumError):  # add_exception_handler chỉ gắn cho ForumError
        raise exc
    if exc.retry_after is not None:
        headers["Retry-After"] = str(int(exc.retry_after) + 1)
    return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)}, headers=headers)


# --- Model biên ------------------------------------------------------------------


def _clean_title(value: str) -> str:
    title = " ".join(value.split())
    if not TITLE_MIN <= len(title) <= TITLE_MAX:
        raise ValueError(f"tiêu đề phải dài {TITLE_MIN}-{TITLE_MAX} ký tự")
    return title


def _clean_body(value: str) -> str:
    # Giữ xuống dòng — đó là định dạng duy nhất của text thuần. Chỉ bỏ khoảng
    # trắng thừa hai đầu.
    body = value.strip()
    if not body:
        raise ValueError("nội dung không được trống")
    if len(body) > BODY_MAX:
        raise ValueError(f"nội dung tối đa {BODY_MAX} ký tự")
    return body


class ThreadCreate(BaseModel):
    category: str | None = None
    game_id: str | None = None
    title: str
    body: str

    _title = field_validator("title")(_clean_title)
    _body = field_validator("body")(_clean_body)


class ThreadEdit(BaseModel):
    title: str | None = None
    body: str | None = None

    @field_validator("title")
    @classmethod
    def _title(cls, value: str | None) -> str | None:
        return None if value is None else _clean_title(value)

    @field_validator("body")
    @classmethod
    def _body(cls, value: str | None) -> str | None:
        return None if value is None else _clean_body(value)

    @model_validator(mode="after")
    def _co_gi_do(self) -> ThreadEdit:
        if self.title is None and self.body is None:
            raise ValueError("cần ít nhất tiêu đề hoặc nội dung")
        return self


class PostCreate(BaseModel):
    body: str
    quote_post_id: str | None = None

    _body = field_validator("body")(_clean_body)


class PostEdit(BaseModel):
    body: str

    _body = field_validator("body")(_clean_body)


class ReportCreate(BaseModel):
    target_type: Literal["thread", "post"]
    target_id: str
    reason: str = Field(min_length=1, max_length=REASON_MAX)


class NicknameSet(BaseModel):
    nickname: str = Field(max_length=100)


class ForumAccess(BaseModel):
    steam_id64: str
    allow: bool = True


class Author(BaseModel):
    id: str
    # None = user chưa đặt biệt danh hoặc đã bị xoá; web tự hiện nhãn thay thế.
    nickname: str | None


class GameRef(BaseModel):
    id: str
    slug: str | None
    title: str | None


class ThreadSummary(BaseModel):
    id: str
    title: str
    category: str | None
    game: GameRef | None
    author: Author
    reply_count: int
    locked: bool
    created_at: dt.datetime
    last_post_at: dt.datetime


class ThreadDetail(ThreadSummary):
    body: str
    edited_at: dt.datetime | None
    # Khác "visible" chỉ khi người xem là chính người viết — xem
    # `forum.get_thread`.
    status: Literal["visible", "hidden", "removed"]


class Quote(BaseModel):
    id: str
    # Cả hai None = bài được trích đã bị ẩn hoặc xoá.
    author: Author | None
    body: str | None


class Post(BaseModel):
    id: str
    author: Author
    body: str
    quote: Quote | None
    created_at: dt.datetime
    edited_at: dt.datetime | None
    status: Literal["visible", "hidden", "removed"]


class Category(BaseModel):
    slug: str
    name: str
    description: str
    thread_count: int


class ThreadList(BaseModel):
    items: list[ThreadSummary]
    # Có khi lọc theo game: trang `/forum/g/:slug` lấy tên + id từ đây.
    game: GameRef | None = None
    total: int
    page: int
    per_page: int


class ThreadPage(BaseModel):
    thread: ThreadDetail
    posts: list[Post]
    total_posts: int
    page: int
    per_page: int


class Created(BaseModel):
    id: str


class Me(BaseModel):
    nickname: str | None
    can_post: bool
    reason: str | None


class ReportResult(BaseModel):
    hidden: bool


# --- Đọc -------------------------------------------------------------------------


@router.get("/categories", response_model=list[Category])
async def list_categories(db: MongoDep) -> list[dict[str, Any]]:
    counts = await forum.category_counts(db)
    return [{**c, "thread_count": counts.get(c["slug"], 0)} for c in forum.categories()]


@router.get("/threads", response_model=ThreadList)
async def list_threads(
    db: MongoDep,
    category: str | None = None,
    game_id: str | None = None,
    game_slug: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
) -> dict[str, Any]:
    items, total, game = await forum.list_threads(
        db, category=category, game_id=game_id, game_slug=game_slug, page=page
    )
    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": THREADS_PER_PAGE,
        "game": game,
    }


@router.get("/threads/{thread_id}", response_model=ThreadPage)
async def get_thread(
    db: MongoDep,
    thread_id: str,
    viewer: Annotated[str | None, Depends(get_optional_user_id)],
    page: Annotated[int, Query(ge=1)] = 1,
) -> dict[str, Any]:
    viewer_id = ObjectId(viewer) if viewer and ObjectId.is_valid(viewer) else None
    result = await forum.get_thread(db, thread_id, page=page, viewer_id=viewer_id)
    return {**result, "page": page, "per_page": POSTS_PER_PAGE}


# --- Tài khoản -------------------------------------------------------------------


@router.get("/me", response_model=Me)
async def me(db: MongoDep, settings: SettingsDep, user_id: UserId) -> dict[str, Any]:
    return await forum.posting_status(db, ObjectId(user_id), forum_open=settings.forum_open)


@router.put("/me/nickname", response_model=Me)
async def set_nickname(
    body: NicknameSet, db: MongoDep, settings: SettingsDep, user_id: UserId
) -> dict[str, Any]:
    await forum.set_nickname(db, ObjectId(user_id), body.nickname)
    return await forum.posting_status(db, ObjectId(user_id), forum_open=settings.forum_open)


# --- Ghi -------------------------------------------------------------------------


async def _poster(db: MongoDep, settings: SettingsDep, user_id: UserId) -> ObjectId:
    oid = ObjectId(user_id)
    await forum.require_poster(db, oid, forum_open=settings.forum_open)
    return oid


Poster = Annotated[ObjectId, Depends(_poster)]


@router.post("/threads", response_model=Created, status_code=status.HTTP_201_CREATED)
async def create_thread(
    body: ThreadCreate, db: MongoDep, clients: ClientsDep, author: Poster
) -> dict[str, str]:
    target = await forum.validate_thread_target(db, category=body.category, game_id=body.game_id)
    await forum.take_token(clients.redis, "thread", author)
    thread_id = await forum.create_thread(
        db, author, target=target, title=body.title, body=body.body
    )
    return {"id": thread_id}


@router.patch("/threads/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
async def edit_thread(thread_id: str, body: ThreadEdit, db: MongoDep, author: Poster) -> Response:
    await forum.edit_thread(db, author, thread_id, title=body.title, body=body.body)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/threads/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_thread(thread_id: str, db: MongoDep, user_id: UserId) -> Response:
    # Xoá bài của chính mình không cần qua cổng beta: người bị thu quyền vẫn
    # phải gỡ được thứ mình đã viết.
    await forum.delete_thread(db, ObjectId(user_id), thread_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/threads/{thread_id}/posts", response_model=Created, status_code=status.HTTP_201_CREATED
)
async def create_post(
    thread_id: str, body: PostCreate, db: MongoDep, clients: ClientsDep, author: Poster
) -> dict[str, str]:
    thread, quote = await forum.validate_reply(db, thread_id, body.quote_post_id)
    await forum.take_token(clients.redis, "post", author)
    post_id = await forum.create_post(db, author, thread, body=body.body, quote_post_id=quote)
    return {"id": post_id}


@router.patch("/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def edit_post(post_id: str, body: PostEdit, db: MongoDep, author: Poster) -> Response:
    await forum.edit_post(db, author, post_id, body=body.body)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(post_id: str, db: MongoDep, user_id: UserId) -> Response:
    await forum.delete_post(db, ObjectId(user_id), post_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/reports", response_model=ReportResult, status_code=status.HTTP_201_CREATED)
async def create_report(
    body: ReportCreate, db: MongoDep, clients: ClientsDep, reporter: Poster
) -> dict[str, bool]:
    target = await forum.validate_report(db, reporter, body.target_type, body.target_id)
    await forum.take_token(clients.redis, "report", reporter)
    hidden = await forum.report(db, reporter, body.target_type, target, reason=body.reason)
    return {"hidden": hidden}


# --- Admin -----------------------------------------------------------------------

admin_router = APIRouter(tags=["forum"])


@admin_router.post("/admin/api/forum/access", dependencies=[AdminAuth])
async def grant_access(body: ForumAccess, db: MongoDep) -> dict[str, Any]:
    if not await forum.set_forum_access(db, body.steam_id64, allow=body.allow):
        raise forum.ForumNotFoundError(
            "chưa có user với steam_id64 này — người đó phải đăng nhập bằng Steam một lần trước"
        )
    return {"steam_id64": body.steam_id64, "forum_access": body.allow}


class ModerateRequest(BaseModel):
    target_type: Literal["thread", "post"]
    target_id: str
    action: Literal["restore", "remove", "lock", "unlock"]
    note: str = Field(default="", max_length=REASON_MAX)


@admin_router.get("/admin/api/forum/queue", dependencies=[AdminAuth])
async def moderation_queue(db: MongoDep) -> dict[str, Any]:
    queue: dict[str, Any] = jsonable(await forum.moderation_queue(db))
    return queue


@admin_router.post("/admin/api/forum/moderate", dependencies=[AdminAuth])
async def moderate(body: ModerateRequest, db: MongoDep) -> dict[str, str]:
    await forum.moderate(db, body.target_type, body.target_id, body.action, note=body.note)
    return {"status": "ok"}


# --- Trang admin (HTML) ------------------------------------------------------------

_DA_LAM = {
    "restore": "khôi phục",
    "remove": "gỡ",
    "lock": "khoá",
    "unlock": "mở khoá",
    "access": "cấp quyền",
}


@admin_router.get("/admin/forum", response_class=HTMLResponse, dependencies=[PageAuth])
async def page_moderation(request: Request, db: MongoDep, done: str = "") -> Response:
    return TEMPLATES.TemplateResponse(
        request,
        "admin/forum.html",
        {
            "queue": await forum.moderation_queue(db),
            "threshold": forum.REPORT_HIDE_THRESHOLD,
            "done": _DA_LAM.get(done, ""),
        },
    )


@admin_router.post("/admin/forum/moderate", dependencies=[PageAuth])
async def page_moderate(
    db: MongoDep,
    target_type: Annotated[str, Form()],
    target_id: Annotated[str, Form()],
    action: Annotated[str, Form()],
) -> Response:
    await forum.moderate(db, target_type, target_id, action)
    return RedirectResponse(f"/admin/forum?done={action}", status_code=status.HTTP_303_SEE_OTHER)


@admin_router.post("/admin/forum/access", dependencies=[PageAuth])
async def page_grant_access(db: MongoDep, steam_id64: Annotated[str, Form()]) -> Response:
    if not await forum.set_forum_access(db, steam_id64.strip(), allow=True):
        raise forum.ForumNotFoundError(
            "chưa có user với steam_id64 này — người đó phải đăng nhập bằng Steam một lần trước"
        )
    return RedirectResponse("/admin/forum?done=access", status_code=status.HTTP_303_SEE_OTHER)
