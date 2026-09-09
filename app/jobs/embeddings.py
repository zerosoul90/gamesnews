"""Job nạp vector cho catalog — `docs/PHASE-6.md` mục 3, tầng 3.

Đây là "đợt nạp vector cho toàn catalog" mà `PROGRESS.md` ghi nợ. Không có nó
thì `entity_matcher.embedding_match` truy vấn một collection rỗng và tầng 3
luôn trượt — vẫn "chạy", chỉ là không bao giờ khớp được gì.

Hai chốt của một job nạp hàng trăm nghìn entity:

1. **Nối tiếp được sau khi worker restart.** Mốc nằm trong Mongo
   (`embedding_hash` trên chính document game), không nằm trong bộ nhớ tiến
   trình — cùng lý lẽ với job bồi chi tiết Steam của Phase 1.
2. **Không sinh lại vector cho entity không đổi.** Mỗi lần embed là một lần trả
   tiền; băm phần văn bản thật sự đem đi embed rồi so, giống hệt cách
   `content_hash` quyết định có ghi Mongo hay không.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.adapters.base import AdapterError
from app.adapters.llm.gemini import GeminiAdapter
from app.core.config import get_settings
from app.services import embeddings
from app.services.catalog import games

logger = logging.getLogger(__name__)

Db = AsyncIOMotorDatabase[dict[str, Any]]

# Số văn bản mỗi lần gọi `batchEmbedContents`. Lô to thì ít request hơn, nhưng
# một lô hỏng là mất cả lô.
BATCH_SIZE = 50
# Số lô mỗi lượt job. Có trần để một lượt job không chạy hàng giờ và chặn hàng
# đợi Arq; lượt sau tự chạy tiếp từ chỗ đang dở.
MAX_BATCHES = 40


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


async def sync_game_embeddings(ctx: dict[str, Any]) -> dict[str, int]:
    """Nạp vector cho những game chưa có, hoặc có mà tên đã đổi."""
    db: Db = ctx["clients"].db
    settings = get_settings()
    gemini = GeminiAdapter(ctx["clients"].http, settings.gemini_api_key.get_secret_value())

    if not gemini.configured:
        logger.error("GEMINI_API_KEY chưa cấu hình, không nạp được vector")
        return {"embedded": 0, "skipped": 0, "batches": 0}

    qdrant = ctx["clients"].qdrant
    await embeddings.ensure_collection(qdrant)

    tally = {"embedded": 0, "skipped": 0, "batches": 0}

    for _ in range(MAX_BATCHES):
        # Chỉ entity chưa có vector, hoặc vector sinh từ một bản tên cũ. Truy
        # vấn này tự thu hẹp sau mỗi lô, nên vòng lặp luôn tiến.
        cursor = games(db).find(
            {"$or": [{"embedding_hash": None}, {"embedding_hash": {"$exists": False}}]},
            {"titles": 1, "aliases": 1},
        ).limit(BATCH_SIZE)
        batch = [doc async for doc in cursor]
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
            # hoặc key sai — chạy tiếp chỉ để hỏng thêm 39 lần nữa.
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
