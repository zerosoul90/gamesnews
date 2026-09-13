"""Job nạp vector cho catalog — `docs/PHASE-6.md` mục 3, tầng 3.

Đây là đợt nạp vector mà `PROGRESS.md` ghi nợ. Không có nó thì
`entity_matcher.embedding_match` truy vấn một collection rỗng và tầng 3 luôn
trượt — vẫn "chạy", chỉ là không bao giờ khớp được gì.

**Không nạp cả catalog, và đó là chủ ý.** Tài liệu ban đầu ghi "một đợt nạp
vector cho toàn catalog"; đo thật ngày 2026-09-13 cho thấy điều đó bất khả với
hạn mức miễn phí: ~100 content/phút, tức 185.231 game là **31 ngày quota
thuần**. Mà phần lớn catalog — nhạc nền, công cụ, game vô danh — không bao giờ
xuất hiện trong một bài tin nào. Job vì thế đi theo tín hiệu (xem `_candidates`)
thay vì quét tuần tự.

Ba chốt:

1. **Nối tiếp được sau khi worker restart.** Mốc nằm trong Mongo
   (`embedding_hash` trên chính document game), không nằm trong bộ nhớ tiến
   trình — cùng lý lẽ với job bồi chi tiết Steam của Phase 1.
2. **Không sinh lại vector cho entity không đổi.** Mỗi lần embed là một lần trả
   tiền; băm phần văn bản thật sự đem đi embed rồi so, giống hệt cách
   `content_hash` quyết định có ghi Mongo hay không.
3. **Có trần quota mỗi lượt.** Job này và `crawl_all_sources` dùng chung một
   hạn mức Gemini; vét sạch là bỏ đói việc dịch tin, thứ mà `PHASE-6.md` gọi là
   giá trị lõi.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.adapters.base import AdapterError, RedisTokenBucket
from app.adapters.llm.gemini import EMBED_RATE, GeminiAdapter
from app.core.config import get_settings
from app.services import embeddings
from app.services.catalog import games

logger = logging.getLogger(__name__)

Db = AsyncIOMotorDatabase[dict[str, Any]]

# Số văn bản mỗi lần gọi `batchEmbedContents`.
#
# Gộp lô **KHÔNG tiết kiệm quota** — chú thích cũ ở đây tin ngược lại. Đo thật
# 2026-09-13 với key free: lượt đầu nạp đúng 100 rồi 429, lượt sau nạp 50 rồi
# 429, khớp với trần ~100 request/phút. Nghĩa là Google tính **mỗi content là
# một request**, không phải mỗi lời gọi HTTP. Lô chỉ tiết kiệm vòng mạng.
#
# Vì vậy lô nhỏ lại: một lô hỏng là mất cả lô, mà lô to không đổi lại được gì.
BATCH_SIZE = 25

# Trần văn bản mỗi lượt job. Con số này canh hạn mức **NGÀY**, không phải phút.
#
# Token bucket chỉ biết nhịp; nó không đỡ được hạn mức ngày. Đo 2026-09-13:
# `embed_content_free_tier_requests` báo `trần=1000` và tới lúc cạn thì **kể cả
# lô một content cũng bị từ chối**, `retryDelay` đếm ngược về mốc cửa sổ. 1000
# khớp đúng hạn mức ngày của tầng free.
#
# Cron chạy mỗi giờ, tức 24 lượt mỗi ngày. `40 x 24 = 960`, vừa dưới 1000 và
# còn chừa chỗ cho tầng 4 gắn entity — nó embed tên game trên cùng hạn mức này.
# Đặt bằng sức chứa một phút (80) thì ra 1920/ngày, tức nửa ngày sau là mọi lời
# gọi đều 429: vẫn là "một job làm cạn quota của job khác", chỉ chậm hơn.
MAX_TEXTS_PER_RUN = 40

# Ngưỡng "đủ nổi tiếng để có ngày được nhắc trong một bài tin game".
#
# Vì sao phải có ngưỡng: catalog đang trên đường tới 185.231 game, mà ở 100
# content/phút thì nhúng hết là **31 ngày quota thuần**, không làm gì khác. Và
# phần lớn trong số đó — nhạc nền, công cụ, game vô danh — sẽ không bao giờ
# xuất hiện trong một bài tin nào, nên vector của chúng là tiền đổ đi.
#
# Tầng 3 chỉ cần phủ những game mà báo chí thật sự viết về. Số review Steam là
# thứ xấp xỉ điều đó tốt nhất trong những gì ta đang có.
MIN_REVIEWS_FOR_EMBEDDING = 500


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


CHUA_CO_VECTOR: dict[str, Any] = {
    "$or": [{"embedding_hash": None}, {"embedding_hash": {"$exists": False}}]
}


def _as_object_ids(raw: list[Any]) -> list[ObjectId]:
    """Lọc lấy ObjectId hợp lệ từ một danh sách trộn chuỗi và ObjectId.

    Cần thật: `game_hotness` và `articles` lưu `game_id` dưới dạng **chuỗi**,
    còn `game_reviews` lưu **ObjectId**. Tra bằng sai kiểu thì truy vấn không
    lỗi, nó chỉ lặng lẽ không khớp gì — đúng kiểu hỏng đã làm cảnh báo giá chưa
    từng bắn lần nào (xem `tests/test_pricing.py`).
    """
    out: list[ObjectId] = []
    for value in raw:
        if isinstance(value, ObjectId):
            out.append(value)
        elif isinstance(value, str) and ObjectId.is_valid(value):
            out.append(ObjectId(value))
    return out


async def _uu_tien_cao(db: Db, limit: int) -> list[dict[str, Any]]:
    """Game có tín hiệu trực tiếp: đã lên tin, hoặc đang trong bảng hot.

    Tập này nhỏ nhưng đáng giá nhất. Một game đã được nhắc trong tin một lần
    thì sẽ được nhắc lại, và lần sau có thể không kèm link store (tầng 1 trượt)
    cũng không trùng alias nào (tầng 2 trượt) — đúng lúc tầng 3 phải đỡ.
    """
    ids = _as_object_ids(await db.articles.distinct("game_id", {"game_id": {"$ne": None}}))
    ids += _as_object_ids(await db.game_hotness.distinct("game_id"))
    if not ids:
        return []

    cursor = (
        games(db)
        .find(
            {"$and": [{"_id": {"$in": ids}}, CHUA_CO_VECTOR]},
            {"titles": 1, "aliases": 1},
        )
        .limit(limit)
    )
    return [doc async for doc in cursor]


async def _theo_do_noi_tieng(db: Db, limit: int) -> list[dict[str, Any]]:
    """Game nhiều review Steam nhất mà chưa có vector.

    Đi TỪ `game_reviews` chứ không từ `games`: lọc ở phía `games` thì phải dựng
    một danh sách `$in` dài hàng chục nghìn id. Ở đây `$sort` + `$limit` làm
    việc đó, và nạp từ game nổi tiếng nhất xuống — nếu quota chỉ đủ một phần thì
    phần được nạp là phần đáng nạp.
    """
    pipeline: list[dict[str, Any]] = [
        {"$match": {"total": {"$gte": MIN_REVIEWS_FOR_EMBEDDING}}},
        {"$sort": {"total": -1}},
        {"$lookup": {"from": "games", "localField": "game_id", "foreignField": "_id", "as": "g"}},
        {"$unwind": "$g"},
        {"$match": {"$or": [{"g.embedding_hash": None}, {"g.embedding_hash": {"$exists": False}}]}},
        {"$limit": limit},
        {"$replaceRoot": {"newRoot": "$g"}},
        {"$project": {"titles": 1, "aliases": 1}},
    ]
    return [doc async for doc in db.game_reviews.aggregate(pipeline)]


async def _candidates(db: Db, limit: int) -> list[dict[str, Any]]:
    """Lô game đáng nhúng tiếp theo, ưu tiên cao trước."""
    batch = await _uu_tien_cao(db, limit)
    if len(batch) >= limit:
        return batch

    seen = {doc["_id"] for doc in batch}
    for doc in await _theo_do_noi_tieng(db, limit - len(batch)):
        if doc["_id"] not in seen:
            batch.append(doc)
    return batch


async def sync_game_embeddings(ctx: dict[str, Any]) -> dict[str, int]:
    """Nạp vector cho những game chưa có, hoặc có mà tên đã đổi."""
    db: Db = ctx["clients"].db
    settings = get_settings()
    api_key = settings.gemini_api_key.get_secret_value()
    # Cùng lý do như `jobs/news.py`: `RedisTokenBucket` đòi một Redis thật ngay
    # lúc khởi tạo, mà không key thì chẳng có lời gọi nào để giãn nhịp.
    gemini = GeminiAdapter(
        ctx["clients"].http,
        api_key,
        RedisTokenBucket(ctx["clients"].redis, "gemini_embed", EMBED_RATE) if api_key else None,
    )

    if not gemini.configured:
        logger.error("GEMINI_API_KEY chưa cấu hình, không nạp được vector")
        return {"embedded": 0, "skipped": 0, "batches": 0}

    qdrant = ctx["clients"].qdrant
    await embeddings.ensure_collection(qdrant)

    tally = {"embedded": 0, "skipped": 0, "batches": 0}

    while tally["embedded"] + tally["skipped"] < MAX_TEXTS_PER_RUN:
        # Chỉ entity chưa có vector, và chỉ trong tập đáng nhúng. Truy vấn tự
        # thu hẹp sau mỗi lô (lô trước đã được ghi `embedding_hash`), nên vòng
        # lặp luôn tiến.
        con_lai = MAX_TEXTS_PER_RUN - tally["embedded"] - tally["skipped"]
        batch = await _candidates(db, min(BATCH_SIZE, con_lai))
        if not batch:
            break

        payload: list[tuple[Any, str, str]] = []
        for doc in batch:
            text = embeddings.embedding_text(doc)
            if not text:
                # Entity không có tên nào dùng được. Đánh dấu để lượt sau không
                # nhặt lại nó mãi — đây là lý do vòng lặp không kẹt vô hạn.
                await games(db).update_one(
                    {"_id": doc["_id"]}, {"$set": {"embedding_hash": "empty"}}
                )
                tally["skipped"] += 1
                continue
            payload.append((doc["_id"], text, text_hash(text)))

        if not payload:
            continue

        try:
            vectors = await gemini.embed([text for _, text, _ in payload])
        except AdapterError as exc:
            # Dừng lượt, không bỏ qua lô. Lỗi ở đây gần như luôn là hết quota
            # hoặc key sai — chạy tiếp chỉ để hỏng thêm vài lần nữa, và mỗi lần
            # hỏng vẫn ăn vào hạn mức mà job tin tức đang cần.
            logger.warning("dừng lượt nạp vector", extra={"error": repr(exc)})
            break

        await embeddings.upsert_games(
            qdrant,
            [
                (game_id, text, vector)
                for (game_id, text, _), vector in zip(payload, vectors, strict=True)
            ],
        )

        # Ghi mốc SAU khi Qdrant nhận. Ghi trước thì một lần Qdrant hỏng là
        # entity coi như đã nạp mãi mãi mà thật ra không có vector nào.
        for game_id, _, digest in payload:
            await games(db).update_one({"_id": game_id}, {"$set": {"embedding_hash": digest}})

        tally["embedded"] += len(payload)
        tally["batches"] += 1

    logger.info("nạp vector catalog", extra=tally)
    return tally
