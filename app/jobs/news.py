"""Job thu thập tin — `docs/PHASE-6.md`.

Trước lượt này, Phase 6 có đủ **mọi mảnh** mà không có sợi dây nào nối chúng:
`services/crawler.crawl_rss`, `services/dedup`, `services/entity_matcher`,
`services/entity_review`, `services/sources.update_last_crawled` — không hàm
nào được gọi từ bất cứ đâu ngoài test. `WorkerSettings.functions` không có job
tin nào, nên chưa từng có một bài viết nào đi vào `articles`. Nhìn từ
`PROGRESS.md` thì Phase 6 đã xong; nhìn từ hệ thống đang chạy thì nó chưa bắt
đầu.

Thứ tự các bước không phải tuỳ tiện, mỗi bước đứng trước một bước tốn tiền hơn:

1. **Đã thấy URL này chưa** — index unique, rẻ nhất, loại phần lớn.
2. **Simhash** — cùng một tin do năm trang chép lại của nhau. Còn ở trong máy.
3. **Gắn entity** — tầng 1 và 2 chỉ đọc Mongo; tầng 3 mới gọi Gemini.
4. **Tóm tắt + dịch** — đắt nhất, và chỉ chạy cho bài đã qua được ba bước trên.

Đảo thứ tự này thì hoá đơn LLM tính cả trên những bài trùng lặp sẽ bị vứt đi
ngay sau đó.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING, IndexModel
from pymongo.errors import DuplicateKeyError

from app.adapters.base import AdapterError
from app.adapters.llm.gemini import GeminiAdapter
from app.core.config import get_settings
from app.models.article import NewsArticle
from app.models.source import Source
from app.services import entity_review
from app.services.crawler import crawl_rss
from app.services.dedup import is_duplicate
from app.services.entity_matcher import match_entity
from app.services.sources import update_last_crawled

logger = logging.getLogger(__name__)

Db = AsyncIOMotorDatabase[dict[str, Any]]

ARTICLES = "articles"

# Cửa sổ so trùng. Một tin được chép lại trong vòng vài ngày; so với cả kho thì
# vừa chậm vừa dễ gộp nhầm hai tin khác nhau của hai đợt khác nhau.
DEDUP_WINDOW = dt.timedelta(days=3)
# Trần số bài đem ra so simhash. So là O(n) trên từng bài mới, nên phải có trần.
DEDUP_CANDIDATES = 500

INDEXES: list[IndexModel] = [
    # Chốt chống trùng rẻ nhất: cùng một URL không bao giờ vào kho hai lần, kể
    # cả khi job chạy lại giữa chừng.
    IndexModel([("url", ASCENDING)], name="url_unique", unique=True),
    # Truy vấn của cửa sổ dedup, và của trang danh sách tin.
    IndexModel([("published_at", DESCENDING)], name="published_at"),
    # `price_tier._warm_game_ids` lọc theo đúng cặp này.
    IndexModel([("game_id", ASCENDING), ("published_at", DESCENDING)], name="game_published"),
    IndexModel([("status", ASCENDING)], name="status"),
]


async def ensure_indexes(db: Db) -> list[str]:
    return await db[ARTICLES].create_indexes(INDEXES)


async def _recent_hashes(db: Db, now: dt.datetime) -> list[str]:
    """Simhash của các bài gần đây, để so trùng."""
    since = (now - DEDUP_WINDOW).isoformat()
    cursor = (
        db[ARTICLES]
        .find({"published_at": {"$gte": since}}, {"simhash": 1})
        .sort("published_at", DESCENDING)
        .limit(DEDUP_CANDIDATES)
    )
    return [doc["simhash"] async for doc in cursor if doc.get("simhash")]


async def crawl_all_sources(ctx: dict[str, Any]) -> dict[str, int]:
    """Kéo mọi nguồn đang bật, khử trùng, gắn entity, tóm tắt, rồi ghi xuống.

    Trả về số đếm từng bước — đây là bảng điều khiển duy nhất của Phase 6, và
    checkpoint "gắn entity tự động >= 85%" đọc thẳng từ `tally`:
    `(exact + alias + embedding) / stored`.
    """
    db: Db = ctx["clients"].db
    settings = get_settings()

    await ensure_indexes(db)
    await entity_review.ensure_indexes(db)

    gemini = GeminiAdapter(ctx["clients"].http, settings.gemini_api_key.get_secret_value())
    if not gemini.configured:
        # Vẫn chạy: crawl và gắn entity ở tầng 1-2 không cần LLM. Nhưng phải
        # báo to, vì bản tin sẽ ra feed dưới dạng tiếng Anh chưa tóm tắt và
        # người vận hành cần biết vì sao.
        logger.warning("GEMINI_API_KEY chưa cấu hình: bỏ qua bước tóm tắt và dịch")

    now = dt.datetime.now(dt.UTC)
    seen_hashes = await _recent_hashes(db, now)

    tally = {
        "sources": 0,
        "fetched": 0,
        "duplicate": 0,
        "already_seen": 0,
        "stored": 0,
        "exact": 0,
        "alias": 0,
        "embedding": 0,
        "manual": 0,
        "summarized": 0,
    }

    async for source_doc in db.sources.find({"status": "active"}):
        source_id: ObjectId = source_doc["_id"]
        try:
            source = Source(**{k: v for k, v in source_doc.items() if k != "_id"})
        except (TypeError, ValueError) as exc:
            logger.warning(
                "nguồn có dữ liệu không hợp lệ, bỏ qua",
                extra={"source_id": str(source_id), "error": str(exc)},
            )
            continue

        tally["sources"] += 1
        articles = await crawl_rss(source)
        tally["fetched"] += len(articles)

        for article in articles:
            # Nguồn là _id thật, không phải tên. Tên nguồn đổi được, và đổi rồi
            # thì mọi bài cũ mất đường về nguồn của nó.
            article.source_id = str(source_id)

            if await db[ARTICLES].find_one({"url": article.url}, {"_id": 1}):
                tally["already_seen"] += 1
                continue

            if any(is_duplicate(article.simhash, seen) for seen in seen_hashes):
                article.status = "duplicate"
                tally["duplicate"] += 1
                await _insert(db, article)
                continue

            match = await match_entity(
                db,
                article.title,
                article.original_content,
                qdrant_client=ctx["clients"].qdrant,
                gemini=gemini if gemini.configured else None,
            )
            article.matching_tier = match.tier if match.matched else "none"
            article.confidence_score = match.confidence
            article.game_id = str(match.game_id) if match.game_id else None
            tally[match.tier if match.matched else "manual"] += 1

            if gemini.configured:
                try:
                    parsed = await gemini.summarize_and_translate(
                        title=article.title, content=article.original_content
                    )
                except AdapterError as exc:
                    # Bài vẫn được lưu, chỉ là chưa có bản tiếng Việt. Vứt cả
                    # bài đi vì một lần gọi LLM hỏng là mất tin thật.
                    parsed = None
                    logger.warning(
                        "gọi LLM hỏng, lưu bài dạng chưa dịch",
                        extra={"url": article.url, "error": repr(exc)},
                    )
                if parsed is not None:
                    article.translated_title = parsed.translated_title
                    article.summary_vi = parsed.summary_vi
                    tally["summarized"] += 1

            article_id = await _insert(db, article)
            if article_id is None:
                # Job khác vừa chèn đúng URL này (index unique chặn). Không
                # phải lỗi, chỉ là ta thua cuộc đua.
                tally["already_seen"] += 1
                continue

            tally["stored"] += 1
            seen_hashes.append(article.simhash)

            if not match.matched:
                await entity_review.enqueue(
                    db, article_id=article_id, title=article.title, url=article.url
                )

        await update_last_crawled(db, source_id)

    logger.info("crawl tin: xong lượt", extra=tally)
    return tally


async def _insert(db: Db, article: NewsArticle) -> ObjectId | None:
    """Ghi một bài. None nếu URL đã tồn tại (index unique chặn)."""
    try:
        result = await db[ARTICLES].insert_one(article.to_mongo())
    except DuplicateKeyError:
        return None
    inserted: ObjectId = result.inserted_id
    return inserted
