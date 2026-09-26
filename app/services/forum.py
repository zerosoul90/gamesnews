"""Diễn đàn — luật dữ liệu và cổng đăng bài ở `docs/FORUM.md`.

Service không biết gì về HTTP: lỗi nghiệp vụ là `ForumError` mang sẵn mã
trạng thái, và `app/main.py` đổi nó thành JSON ở đúng một chỗ.
"""

from __future__ import annotations

import datetime as dt
import functools
import json
from pathlib import Path
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING, IndexModel
from pymongo.errors import DuplicateKeyError
from redis.asyncio import Redis

from app.adapters.base import RateLimit, RedisTokenBucket
from app.services.normalize import normalize_vi

Db = AsyncIOMotorDatabase[dict[str, Any]]

THREADS = "forum_threads"
POSTS = "forum_posts"
REPORTS = "forum_reports"

VISIBLE = "visible"
HIDDEN = "hidden"
DELETED = "deleted"

THREADS_PER_PAGE = 20
POSTS_PER_PAGE = 30

# Ba người khác nhau, không phải ba lượt: mỗi người chỉ báo được một lần cho
# mỗi bài (index unique ở dưới). Thấp hơn thì một người lập hai tài khoản là ẩn
# được bài của người khác; cao hơn thì giai đoạn beta ít người sẽ không bao giờ
# chạm ngưỡng.
REPORT_HIDE_THRESHOLD = 3

NICKNAME_MIN = 3
NICKNAME_MAX = 24
NICKNAME_COOLDOWN = dt.timedelta(days=30)
_NICKNAME_PUNCT = frozenset(" _.-")

# Theo từng user. Đủ rộng cho người thảo luận thật, đủ hẹp để một tài khoản bị
# chiếm không xả được vài trăm bài trước khi có người để ý.
RATE_LIMITS: dict[str, RateLimit] = {
    "thread": RateLimit(capacity=5, per_seconds=3600),
    "post": RateLimit(capacity=30, per_seconds=3600),
    "report": RateLimit(capacity=20, per_seconds=3600),
}

_DATA_DIR = Path(__file__).parent


# --- Lỗi -----------------------------------------------------------------------


class ForumError(Exception):
    status_code = 400

    def __init__(self, message: str, *, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class ForumValidationError(ForumError):
    status_code = 422


class ForumNotFoundError(ForumError):
    status_code = 404


class ForumForbiddenError(ForumError):
    status_code = 403


class ForumConflictError(ForumError):
    status_code = 409


class ForumRateLimitedError(ForumError):
    status_code = 429


# --- Dữ liệu tĩnh ---------------------------------------------------------------


@functools.cache
def categories() -> tuple[dict[str, str], ...]:
    raw = json.loads((_DATA_DIR / "forum_categories.json").read_text(encoding="utf-8"))
    return tuple(raw)


def category_slugs() -> frozenset[str]:
    return frozenset(c["slug"] for c in categories())


@functools.cache
def _reserved() -> tuple[frozenset[str], tuple[str, ...]]:
    raw = json.loads((_DATA_DIR / "forum_reserved_names.json").read_text(encoding="utf-8"))
    return frozenset(raw["exact"]), tuple(raw["contains"])


# --- Index -------------------------------------------------------------------


async def ensure_indexes(db: Db) -> list[str]:
    names = await db[THREADS].create_indexes(
        [
            IndexModel(
                [("category", ASCENDING), ("status", ASCENDING), ("last_post_at", DESCENDING)],
                name="theo_chuyen_muc",
            ),
            IndexModel(
                [("game_id", ASCENDING), ("status", ASCENDING), ("last_post_at", DESCENDING)],
                name="theo_game",
            ),
            IndexModel([("author_id", ASCENDING), ("created_at", DESCENDING)], name="theo_tac_gia"),
        ]
    )
    names += await db[POSTS].create_indexes(
        [
            IndexModel(
                [("thread_id", ASCENDING), ("status", ASCENDING), ("created_at", ASCENDING)],
                name="theo_chu_de",
            ),
        ]
    )
    names += await db[REPORTS].create_indexes(
        [
            IndexModel(
                [("target_type", ASCENDING), ("target_id", ASCENDING), ("reporter_id", ASCENDING)],
                name="moi_nguoi_bao_mot_lan",
                unique=True,
            ),
        ]
    )
    # Partial chứ không sparse: user chưa đặt biệt danh không có field này, và
    # hàng chục nghìn document thiếu field không được tính là trùng nhau.
    names += await db.users.create_indexes(
        [
            IndexModel(
                [("nickname_key", ASCENDING)],
                name="biet_danh_duy_nhat",
                unique=True,
                partialFilterExpression={"nickname_key": {"$exists": True}},
            ),
        ]
    )
    return names


# --- Biệt danh ---------------------------------------------------------------


def clean_nickname(raw: str) -> str:
    """Biệt danh đã chuẩn hoá để hiển thị. Sai luật thì `ForumValidationError`."""
    # Không dùng `normalize.collapse_spaces`: tên nghe như "gộp khoảng trắng"
    # nhưng nó chuẩn hoá rồi viết liền ("Trần Văn" -> "tranvan").
    name = " ".join(raw.split())
    if not NICKNAME_MIN <= len(name) <= NICKNAME_MAX:
        raise ForumValidationError(f"biệt danh phải dài {NICKNAME_MIN}-{NICKNAME_MAX} ký tự")
    if any(not (ch.isalnum() or ch in _NICKNAME_PUNCT) for ch in name):
        raise ForumValidationError("biệt danh chỉ gồm chữ, số, khoảng trắng và _ . -")

    key = nickname_key(name)
    # "._-a" qua được luật độ dài nhưng khoá chỉ còn "a".
    if len(key) < NICKNAME_MIN:
        raise ForumValidationError(f"biệt danh phải có ít nhất {NICKNAME_MIN} chữ hoặc số")
    exact, contains = _reserved()
    if key in exact or any(word in key for word in contains):
        raise ForumValidationError("biệt danh này không dùng được")
    return name


def nickname_key(name: str) -> str:
    """Khoá so trùng: "Trần Văn", "tran.van", "TRANVAN" là một tên.

    Chặn giả danh bằng cách thêm dấu hay dấu chấm — thứ mà mắt người không
    phân biệt kịp khi lướt qua một luồng thảo luận.
    """
    return normalize_vi(name).replace(" ", "")


async def set_nickname(
    db: Db, user_id: ObjectId, raw: str, *, now: dt.datetime | None = None
) -> str:
    now = now or dt.datetime.now(dt.UTC)
    user = await db.users.find_one({"_id": user_id}, {"nickname_key": 1, "nickname_changed_at": 1})
    if user is None:
        raise ForumNotFoundError("không tìm thấy người dùng")

    name = clean_nickname(raw)
    key = nickname_key(name)
    update: dict[str, Any] = {"nickname": name}

    # Cùng khoá = chỉ sửa hoa/thường hay dấu: vẫn là tên đó, không tính lượt đổi.
    if key != user.get("nickname_key"):
        changed_at = user.get("nickname_changed_at")
        if user.get("nickname_key") and changed_at and now - changed_at < NICKNAME_COOLDOWN:
            next_at = (changed_at + NICKNAME_COOLDOWN).date().isoformat()
            raise ForumConflictError(f"chỉ đổi biệt danh 30 ngày một lần — lần tới: {next_at}")
        update |= {"nickname_key": key, "nickname_changed_at": now}

    try:
        await db.users.update_one({"_id": user_id}, {"$set": update})
    except DuplicateKeyError as exc:
        raise ForumConflictError("biệt danh này đã có người dùng") from exc
    return name


# --- Cổng đăng bài -------------------------------------------------------------


async def posting_status(db: Db, user_id: ObjectId, *, forum_open: bool) -> dict[str, Any]:
    """Trạng thái cho web hiển thị: đăng được chưa, và nếu chưa thì vì sao."""
    user = await db.users.find_one({"_id": user_id}, {"nickname": 1, "forum_access": 1})
    if user is None:
        return {"nickname": None, "can_post": False, "reason": "không tìm thấy người dùng"}
    reason = None
    if not (forum_open or user.get("forum_access")):
        reason = "diễn đàn đang beta kín — chưa được cấp quyền đăng bài"
    elif not user.get("nickname"):
        reason = "cần đặt biệt danh trước khi đăng bài"
    return {"nickname": user.get("nickname"), "can_post": reason is None, "reason": reason}


async def require_poster(db: Db, user_id: ObjectId, *, forum_open: bool) -> None:
    status = await posting_status(db, user_id, forum_open=forum_open)
    if not status["can_post"]:
        raise ForumForbiddenError(status["reason"])


async def take_token(redis: Redis, kind: str, user_id: ObjectId) -> None:
    """Lấy một token của user cho loại hành động này, không chờ.

    Gọi SAU mọi bước kiểm tra: một request sai (chuyên mục không tồn tại, chủ đề
    đã khoá) không được đốt lượt của người dùng.
    """
    bucket = RedisTokenBucket(redis, f"forum:{kind}:{user_id}", RATE_LIMITS[kind])
    wait = await bucket.try_acquire()
    if wait:
        raise ForumRateLimitedError(
            f"đăng quá nhanh — thử lại sau {int(wait) + 1} giây", retry_after=wait
        )


# --- Đọc -----------------------------------------------------------------------


def _oid(value: str, what: str) -> ObjectId:
    if not ObjectId.is_valid(value):
        raise ForumNotFoundError(f"không tìm thấy {what}")
    return ObjectId(value)


async def _authors(db: Db, ids: set[ObjectId]) -> dict[ObjectId, str | None]:
    """Biệt danh theo user id. Chỉ chiếu đúng `nickname`: API diễn đàn không bao
    giờ được lộ `steam_id64`."""
    if not ids:
        return {}
    cursor = db.users.find({"_id": {"$in": list(ids)}}, {"nickname": 1})
    return {doc["_id"]: doc.get("nickname") async for doc in cursor}


async def _games(db: Db, ids: set[ObjectId]) -> dict[ObjectId, dict[str, Any]]:
    if not ids:
        return {}
    cursor = db.games.find({"_id": {"$in": list(ids)}}, {"slug": 1, "titles": 1})
    return {
        doc["_id"]: {
            "id": str(doc["_id"]),
            "slug": doc.get("slug"),
            "title": (doc.get("titles") or {}).get("vi")
            or (doc.get("titles") or {}).get("primary"),
        }
        async for doc in cursor
    }


def _author(authors: dict[ObjectId, str | None], user_id: ObjectId) -> dict[str, Any]:
    return {"id": str(user_id), "nickname": authors.get(user_id)}


async def category_counts(db: Db) -> dict[str, int]:
    pipeline: list[dict[str, Any]] = [
        {"$match": {"status": VISIBLE, "category": {"$ne": None}}},
        {"$group": {"_id": "$category", "n": {"$sum": 1}}},
    ]
    return {doc["_id"]: doc["n"] async for doc in db[THREADS].aggregate(pipeline)}


async def list_threads(
    db: Db, *, category: str | None, game_id: str | None, page: int
) -> tuple[list[dict[str, Any]], int]:
    query: dict[str, Any] = {"status": VISIBLE}
    if category is not None:
        if category not in category_slugs():
            raise ForumNotFoundError("không tìm thấy chuyên mục")
        query["category"] = category
    if game_id is not None:
        query["game_id"] = _oid(game_id, "game")

    total = await db[THREADS].count_documents(query)
    cursor = (
        db[THREADS]
        .find(query, {"body": 0})
        .sort("last_post_at", DESCENDING)
        .skip((page - 1) * THREADS_PER_PAGE)
        .limit(THREADS_PER_PAGE)
    )
    docs = [doc async for doc in cursor]
    authors = await _authors(db, {d["author_id"] for d in docs})
    games = await _games(db, {d["game_id"] for d in docs if d.get("game_id")})
    return [_thread_summary(d, authors, games) for d in docs], total


def _thread_summary(
    doc: dict[str, Any],
    authors: dict[ObjectId, str | None],
    games: dict[ObjectId, dict[str, Any]],
) -> dict[str, Any]:
    return {
        "id": str(doc["_id"]),
        "title": doc["title"],
        "category": doc.get("category"),
        "game": games.get(doc["game_id"]) if doc.get("game_id") else None,
        "author": _author(authors, doc["author_id"]),
        "reply_count": doc.get("reply_count", 0),
        "locked": doc.get("locked", False),
        "created_at": doc["created_at"],
        "last_post_at": doc["last_post_at"],
    }


async def _visible_thread(db: Db, thread_id: str) -> dict[str, Any]:
    doc = await db[THREADS].find_one({"_id": _oid(thread_id, "chủ đề"), "status": VISIBLE})
    if doc is None:
        # Bị ẩn và bị xoá cũng là 404: nói "bài này bị ẩn" với người lạ là để lộ
        # đúng thứ mà việc ẩn muốn giấu.
        raise ForumNotFoundError("không tìm thấy chủ đề")
    return doc


async def get_thread(db: Db, thread_id: str, *, page: int) -> dict[str, Any]:
    thread = await _visible_thread(db, thread_id)
    query = {"thread_id": thread["_id"], "status": VISIBLE}
    total = await db[POSTS].count_documents(query)
    cursor = (
        db[POSTS]
        .find(query)
        .sort("created_at", ASCENDING)
        .skip((page - 1) * POSTS_PER_PAGE)
        .limit(POSTS_PER_PAGE)
    )
    posts = [doc async for doc in cursor]

    quote_ids = {p["quote_post_id"] for p in posts if p.get("quote_post_id")}
    quotes = (
        {
            doc["_id"]: doc
            async for doc in db[POSTS].find(
                {"_id": {"$in": list(quote_ids)}}, {"author_id": 1, "body": 1, "status": 1}
            )
        }
        if quote_ids
        else {}
    )

    authors = await _authors(
        db,
        {thread["author_id"]}
        | {p["author_id"] for p in posts}
        | {q["author_id"] for q in quotes.values()},
    )
    games = await _games(db, {thread["game_id"]} if thread.get("game_id") else set())

    return {
        "thread": {
            **_thread_summary(thread, authors, games),
            "body": thread["body"],
            "edited_at": thread.get("edited_at"),
        },
        "posts": [_post(p, authors, quotes) for p in posts],
        "total_posts": total,
    }


def _post(
    doc: dict[str, Any],
    authors: dict[ObjectId, str | None],
    quotes: dict[ObjectId, dict[str, Any]],
) -> dict[str, Any]:
    quote = None
    if (quote_id := doc.get("quote_post_id")) is not None:
        source = quotes.get(quote_id)
        # Bài được trích sau đó bị ẩn/xoá thì bỏ nội dung, giữ dấu vết. Không
        # thì trích dẫn thành đường vòng để đọc bài đã bị kiểm duyệt gỡ.
        if source is not None and source.get("status") == VISIBLE:
            quote = {
                "id": str(quote_id),
                "author": _author(authors, source["author_id"]),
                "body": source["body"],
            }
        else:
            quote = {"id": str(quote_id), "author": None, "body": None}
    return {
        "id": str(doc["_id"]),
        "author": _author(authors, doc["author_id"]),
        "body": doc["body"],
        "quote": quote,
        "created_at": doc["created_at"],
        "edited_at": doc.get("edited_at"),
    }


# --- Ghi -----------------------------------------------------------------------


async def validate_thread_target(
    db: Db, *, category: str | None, game_id: str | None
) -> dict[str, Any]:
    """Đúng một trong hai: chuyên mục chung, hoặc khu thảo luận của một game."""
    if (category is None) == (game_id is None):
        raise ForumValidationError("chủ đề phải thuộc đúng một chuyên mục hoặc một game")
    if category is not None:
        if category not in category_slugs():
            raise ForumNotFoundError("không tìm thấy chuyên mục")
        return {"category": category, "game_id": None}
    oid = _oid(game_id or "", "game")
    if await db.games.count_documents({"_id": oid}, limit=1) == 0:
        raise ForumNotFoundError("không tìm thấy game")
    return {"category": None, "game_id": oid}


async def create_thread(
    db: Db,
    author_id: ObjectId,
    *,
    target: dict[str, Any],
    title: str,
    body: str,
    now: dt.datetime | None = None,
) -> str:
    now = now or dt.datetime.now(dt.UTC)
    result = await db[THREADS].insert_one(
        {
            **target,
            "author_id": author_id,
            "title": title,
            "body": body,
            "status": VISIBLE,
            "locked": False,
            "reply_count": 0,
            "report_count": 0,
            "created_at": now,
            "last_post_at": now,
        }
    )
    return str(result.inserted_id)


async def validate_reply(
    db: Db, thread_id: str, quote_post_id: str | None
) -> tuple[dict[str, Any], ObjectId | None]:
    thread = await _visible_thread(db, thread_id)
    if thread.get("locked"):
        raise ForumConflictError("chủ đề đã khoá, không trả lời được nữa")
    quote_oid = None
    if quote_post_id is not None:
        quote_oid = _oid(quote_post_id, "bài được trích")
        found = await db[POSTS].count_documents(
            {"_id": quote_oid, "thread_id": thread["_id"], "status": VISIBLE}, limit=1
        )
        if not found:
            raise ForumNotFoundError("không tìm thấy bài được trích trong chủ đề này")
    return thread, quote_oid


async def create_post(
    db: Db,
    author_id: ObjectId,
    thread: dict[str, Any],
    *,
    body: str,
    quote_post_id: ObjectId | None,
    now: dt.datetime | None = None,
) -> str:
    now = now or dt.datetime.now(dt.UTC)
    result = await db[POSTS].insert_one(
        {
            "thread_id": thread["_id"],
            "author_id": author_id,
            "body": body,
            "quote_post_id": quote_post_id,
            "status": VISIBLE,
            "report_count": 0,
            "created_at": now,
        }
    )
    await db[THREADS].update_one(
        {"_id": thread["_id"]}, {"$inc": {"reply_count": 1}, "$set": {"last_post_at": now}}
    )
    return str(result.inserted_id)


async def _own(
    db: Db, collection: str, target_id: str, user_id: ObjectId, what: str
) -> dict[str, Any]:
    doc = await db[collection].find_one({"_id": _oid(target_id, what), "status": VISIBLE})
    if doc is None:
        raise ForumNotFoundError(f"không tìm thấy {what}")
    if doc["author_id"] != user_id:
        raise ForumForbiddenError(f"chỉ người viết mới sửa hoặc xoá được {what}")
    return doc


async def edit_thread(
    db: Db, user_id: ObjectId, thread_id: str, *, title: str | None, body: str | None
) -> None:
    doc = await _own(db, THREADS, thread_id, user_id, "chủ đề")
    update: dict[str, Any] = {"edited_at": dt.datetime.now(dt.UTC)}
    if title is not None:
        update["title"] = title
    if body is not None:
        update["body"] = body
    await db[THREADS].update_one({"_id": doc["_id"]}, {"$set": update})


async def edit_post(db: Db, user_id: ObjectId, post_id: str, *, body: str) -> None:
    doc = await _own(db, POSTS, post_id, user_id, "bài trả lời")
    await db[POSTS].update_one(
        {"_id": doc["_id"]}, {"$set": {"body": body, "edited_at": dt.datetime.now(dt.UTC)}}
    )


async def delete_thread(db: Db, user_id: ObjectId, thread_id: str) -> None:
    doc = await _own(db, THREADS, thread_id, user_id, "chủ đề")
    await db[THREADS].update_one({"_id": doc["_id"]}, {"$set": {"status": DELETED}})


async def delete_post(db: Db, user_id: ObjectId, post_id: str) -> None:
    doc = await _own(db, POSTS, post_id, user_id, "bài trả lời")
    await db[POSTS].update_one({"_id": doc["_id"]}, {"$set": {"status": DELETED}})
    await db[THREADS].update_one({"_id": doc["thread_id"]}, {"$inc": {"reply_count": -1}})


# --- Báo cáo -------------------------------------------------------------------

_REPORT_TARGETS = {"thread": THREADS, "post": POSTS}


async def validate_report(
    db: Db, reporter_id: ObjectId, target_type: str, target_id: str
) -> dict[str, Any]:
    collection = _REPORT_TARGETS[target_type]
    doc = await db[collection].find_one({"_id": _oid(target_id, "bài"), "status": VISIBLE})
    if doc is None:
        raise ForumNotFoundError("không tìm thấy bài")
    if doc["author_id"] == reporter_id:
        raise ForumValidationError("không tự báo cáo bài của mình được")
    return doc


async def report(
    db: Db,
    reporter_id: ObjectId,
    target_type: str,
    target: dict[str, Any],
    *,
    reason: str,
    now: dt.datetime | None = None,
) -> bool:
    """Ghi một báo cáo. Trả về True nếu lượt này làm bài bị ẩn."""
    now = now or dt.datetime.now(dt.UTC)
    try:
        await db[REPORTS].insert_one(
            {
                "target_type": target_type,
                "target_id": target["_id"],
                "reporter_id": reporter_id,
                "reason": reason,
                "created_at": now,
            }
        )
    except DuplicateKeyError as exc:
        raise ForumConflictError("bạn đã báo cáo bài này rồi") from exc

    # Đếm lại từ `forum_reports` chứ không `$inc` rồi tin con số đó: đếm từ
    # nguồn thì hai lượt báo cáo đồng thời không làm lệch ngưỡng.
    count = await db[REPORTS].count_documents(
        {"target_type": target_type, "target_id": target["_id"]}
    )
    update: dict[str, Any] = {"report_count": count}
    hide = count >= REPORT_HIDE_THRESHOLD
    if hide:
        update |= {"status": HIDDEN, "hidden_reason": "reports", "hidden_at": now}
    collection = _REPORT_TARGETS[target_type]
    result = await db[collection].update_one(
        {"_id": target["_id"], "status": VISIBLE}, {"$set": update}
    )
    if hide and target_type == "post" and result.modified_count:
        await db[THREADS].update_one({"_id": target["thread_id"]}, {"$inc": {"reply_count": -1}})
    return hide


# --- Admin ---------------------------------------------------------------------


async def set_forum_access(db: Db, steam_id64: str, *, allow: bool) -> bool:
    """Cấp/thu quyền đăng bài trong beta kín. False nếu chưa có user đó —
    người ấy phải đăng nhập bằng Steam ít nhất một lần trước."""
    result = await db.users.update_one(
        {"steam_id64": steam_id64}, {"$set": {"forum_access": allow}}
    )
    return result.matched_count > 0
