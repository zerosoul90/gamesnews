"""Tóm tắt bù cho bài đã nằm trong kho mà chưa có tiếng Việt.

**Vì sao cần một job riêng.** `crawl_all_sources` chỉ dịch bài **ngay lúc ghi
nó xuống**, và không có đường nào quay lại. Hệ quả đo được ngày 2026-09-13:
819/843 bài không có `summary_vi` — chúng vào kho trong những ngày
`GEMINI_API_KEY` còn trống, rồi nằm đó vĩnh viễn dưới dạng tiêu đề tiếng Anh.
Mà `PHASE-6.md` gọi việc đưa tin thế giới sang tiếng Việt là **giá trị lõi** của
cả phase, không phải một thứ trang trí.

Job này cũng là mảnh còn thiếu của luật mới trong `jobs/news.py` ("hết trần LLM
thì để bài lại cho lượt sau, không lưu dạng chưa dịch"): luật đó chỉ đúng chừng
nào có đường quay lại. Nay có.

Ba quyết định đáng ghi:

1. **Bỏ qua bài trùng.** 137/819 bài mang `status: "duplicate"` — chúng không
   bao giờ hiện ra cho ai đọc. Dịch chúng là ném 17% hạn mức qua cửa sổ.
2. **Bài mới nhất trước.** Ngược với `entity_review.pending` (cũ trước): ở đó
   thứ tự công bằng mới đúng, còn ở đây tin cũ đã mất giá trị nên dịch trước
   cái còn đáng đọc. Hàng tồn không bao giờ vơi hết cũng không sao — phần không
   bao giờ tới lượt chính là phần không ai cần nữa.
3. **Gắn lại entity cho bài chưa gắn.** Cùng một lời gọi LLM đã trả về
   `suggested_alias`; vứt nó đi là lặp lại đúng cái sai vừa sửa hôm nay, khi
   trường đó nằm trong prompt từ đầu mà không chỗ nào đọc. 601/682 bài cần dịch
   cũng đang chưa có entity.
"""

from __future__ import annotations

import logging
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.adapters.base import AdapterError, RedisTokenBucket
from app.adapters.llm.gemini import GENERATE_RATE, GeminiAdapter
from app.core.config import get_settings
from app.services import entity_review
from app.services.entity_matcher import match_entity

logger = logging.getLogger(__name__)

Db = AsyncIOMotorDatabase[dict[str, Any]]

ARTICLES = "articles"

# Sàn token chừa lại cho `crawl_all_sources`.
#
# Hai job dùng CHUNG bucket `gemini_generate`, vì chúng dùng chung một hạn mức
# thật. Nhưng chúng không ngang hàng: crawl phải đưa tin mới ra trong 2 giờ
# (`PHASE-6.md`), còn job này xử lý hàng tồn — chậm một lượt không ai thấy.
# Không có sàn thì một lượt bù vét sạch bucket và lượt crawl ngay sau đó không
# dịch nổi bài nào.
#
# Sàn phải NHỎ HƠN `GENERATE_RATE.capacity`, và `RedisTokenBucket.__init__` ném
# `PermanentError` nếu không — nên nó phải được chia lại cùng lúc với capacity,
# không phải một hằng số độc lập. Giữ tỉ lệ ~1/4 như cũ: 2 trên 7.
RESERVE_FOR_CRAWL = 2

# Trần mỗi lượt, cũng là một phép chia trên `GENERATE_RATE`: job này được dùng
# `capacity - RESERVE_FOR_CRAWL` = 5 token/phút, nên 15 bài là ~3 phút — vừa cái
# ngân sách của Arq (giết job ở 300 giây) sau khi trừ phần embedding và Qdrant
# của bước gắn entity.
#
# Cron chạy hàng giờ, nên 15 là ~360 bài/ngày: 692 bài tồn mất khoảng hai ngày.
#
# Hạn mức NGÀY của model mới thì CHƯA đo được — cả phiên đo 2026-09-15 không lần
# nào chạm tới nó, nên chỉ biết nó lớn hơn hẳn 20 của `gemini-2.5-flash`. Không
# cần biết chính xác để an toàn: chạm hạn mức thì `AdapterError` làm job dừng
# lượt, lượt sau chạy tiếp từ chỗ đang dở — mốc nằm trong chính dữ liệu
# (`summary_vi` đã điền hay chưa), không trong bộ nhớ tiến trình. Và nay thân
# lỗi in `quotaId`, nên lúc chạm sẽ đọc ra ngay là chiều NGÀY chứ không phải
# đoán như lần trước.
MAX_ARTICLES_PER_RUN = 15


async def _ung_vien(db: Db, limit: int) -> list[dict[str, Any]]:
    """Bài cần dịch, mới nhất trước."""
    cursor = (
        db[ARTICLES]
        .find(
            {
                "summary_vi": None,
                # Bài trùng không bao giờ hiện ra, dịch là phí hạn mức.
                "status": {"$ne": "duplicate"},
                # Nguồn tiếng Việt bị `crawl_all_sources` bỏ qua bước LLM có chủ
                # ý, nên bài của họ nằm đây với `summary_vi: None` VĨNH VIỄN.
                # Không loại ra thì job này gom đúng chúng về dịch, và khoản
                # tiết kiệm bên kia chỉ là DỜI chi phí sang đây chứ không bỏ đi.
                "source_id": {"$nin": await _nguon_tieng_viet(db)},
            },
            {"title": 1, "original_content": 1, "game_id": 1, "url": 1},
        )
        .sort("published_at", -1)
        .limit(limit)
    )
    return [doc async for doc in cursor]


async def _nguon_tieng_viet(db: Db) -> list[str]:
    """`source_id` của các nguồn tiếng Việt, dạng chuỗi như bài đang lưu.

    Lọc theo NGUỒN chứ không theo một cờ trên từng bài, vì hai lý do: bài cũ vào
    kho từ trước khi có luật này không có cờ nào cả, và đổi `language` của một
    nguồn thì phải có hiệu lực ngay với cả bài cũ của nó.
    """
    return [str(doc["_id"]) async for doc in db.sources.find({"language": "vi"}, {"_id": 1})]


async def backfill_summaries(ctx: dict[str, Any]) -> dict[str, int]:
    """Dịch bù, và gắn lại entity cho bài chưa gắn."""
    db: Db = ctx["clients"].db
    settings = get_settings()

    api_key = settings.gemini_api_key.get_secret_value()
    if not api_key:
        # Khác `crawl_all_sources`: ở đó thiếu key vẫn còn việc để làm (kéo tin,
        # khử trùng, gắn entity hai tầng đầu). Ở đây LLM là toàn bộ công việc.
        logger.warning("GEMINI_API_KEY chưa cấu hình, không tóm tắt bù được")
        return {"checked": 0, "summarized": 0, "matched": 0, "failed": 0}

    gemini = GeminiAdapter(
        ctx["clients"].http,
        api_key,
        RedisTokenBucket(
            ctx["clients"].redis,
            "gemini_generate",
            GENERATE_RATE,
            reserve=RESERVE_FOR_CRAWL,
        ),
    )

    tally = {"checked": 0, "summarized": 0, "matched": 0, "failed": 0}

    for doc in await _ung_vien(db, MAX_ARTICLES_PER_RUN):
        tally["checked"] += 1
        try:
            parsed = await gemini.summarize_and_translate(
                title=doc["title"], content=doc.get("original_content") or ""
            )
        except AdapterError as exc:
            # Dừng lượt, không thử bài tiếp theo. Lỗi ở đây gần như luôn là hết
            # hạn mức, và 24 lần hỏng nữa cũng chỉ ăn thêm quota của job crawl.
            tally["failed"] += 1
            logger.warning("dừng lượt tóm tắt bù", extra={"error": repr(exc)})
            break

        if parsed is None:
            # Model trả về thứ không đọc được. Không phải lỗi hạn mức nên chạy
            # tiếp, nhưng bài này vẫn ở lại hàng tồn cho lượt sau.
            tally["failed"] += 1
            continue

        update: dict[str, Any] = {
            "translated_title": parsed.translated_title,
            "summary_vi": parsed.summary_vi,
        }
        tally["summarized"] += 1

        # Bài chưa có entity thì thử lại với cái tên LLM vừa trích ra. Không tốn
        # thêm lời gọi nào — nó đi kèm bản tóm tắt ở trên.
        if not doc.get("game_id") and parsed.suggested_alias:
            match = await match_entity(
                db,
                doc["title"],
                doc.get("original_content") or "",
                qdrant_client=ctx["clients"].qdrant,
                gemini=gemini,
                suggested_alias=parsed.suggested_alias,
            )
            if match.matched and match.game_id is not None:
                update["game_id"] = str(match.game_id)
                update["matching_tier"] = match.tier
                update["confidence_score"] = match.confidence
                await entity_review.auto_resolve(db, article_id=doc["_id"], game_id=match.game_id)
                tally["matched"] += 1

        await db[ARTICLES].update_one({"_id": doc["_id"]}, {"$set": update})

    logger.info("tóm tắt bù: xong lượt", extra=tally)
    return tally
