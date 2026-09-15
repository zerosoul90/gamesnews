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
3. **Tóm tắt + dịch** — lời gọi LLM duy nhất, và chỉ cho bài đã qua hai bước trên.
4. **Gắn entity** — tầng 1 và 2 chỉ đọc Mongo; hai tầng cuối dùng
   `suggested_alias` mà bước 3 vừa trả về.

Đảo hai bước đầu thì hoá đơn LLM tính cả trên những bài trùng lặp sẽ bị vứt đi
ngay sau đó.

**Bước 3 đứng trước bước 4 chứ không ngược lại** — khác bản đầu. Không phải vì
nó rẻ hơn mà vì bước 4 CẦN đầu ra của nó: `suggested_alias`, tên game do LLM
trích từ bài. Và việc đổi chỗ không tốn thêm đồng nào, vì tóm tắt vốn chạy cho
mọi bài được lưu bất kể gắn được entity hay không. Nó còn tiết kiệm: tầng cuối
chỉ phải sinh vector khi tầng alias của chính cái tên đó cũng trượt.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING, IndexModel
from pymongo.errors import DuplicateKeyError

from app.adapters.base import AdapterError, RedisDailyBudget, RedisTokenBucket
from app.adapters.llm.gemini import GENERATE_DAILY_LIMIT, GENERATE_RATE, GeminiAdapter
from app.core.config import get_settings
from app.models.article import NewsArticle
from app.models.source import Source
from app.services import entity_review
from app.services.crawler import crawl_rss
from app.services.dedup import is_duplicate
from app.services.entity_matcher import match_entity
from app.services.sources import ghi_nhan_so_bai, update_last_crawled

logger = logging.getLogger(__name__)

Db = AsyncIOMotorDatabase[dict[str, Any]]

ARTICLES = "articles"

# Cửa sổ so trùng. Một tin được chép lại trong vòng vài ngày; so với cả kho thì
# vừa chậm vừa dễ gộp nhầm hai tin khác nhau của hai đợt khác nhau.
DEDUP_WINDOW = dt.timedelta(days=3)
# Trần số bài đem ra so simhash. So là O(n) trên từng bài mới, nên phải có trần.
DEDUP_CANDIDATES = 500

# Trần số bài gọi LLM mỗi lượt.
#
# Token bucket giãn nhịp nhưng KHÔNG chặn tổng: một lượt gặp 587 bài mới (đúng
# con số lượt crawl đầu tiên) sẽ ngồi chờ hàng chục phút, trong khi Arq mặc định
# giết job ở 300 giây. Job bị giết giữa chừng không mất dữ liệu — bài đã ghi thì
# ở lại, bài chưa ghi vẫn còn trong feed và lượt sau nhặt lại — nhưng nó chết
# kèm traceback mỗi lượt, che mất những lỗi thật.
#
# Ngân sách phải tính theo THỜI GIAN THẬT của một bài, không chỉ theo thời gian
# chờ token. Mỗi bài tốn ~8,6 giây chờ bucket (nhịp 7/phút) CỘNG một lời gọi
# embedding và một truy vấn Qdrant của bước gắn entity — đo được ~12 giây/bài.
#
# Đặt 21 thì riêng phần LLM đã ~250 giây, và lượt 10:50 ngày 2026-09-15 chết
# `TimeoutError` ở 299,99 giây với traceback dừng ngay trong `limiter.acquire`.
# 10 bài là ~120 giây, chừa hơn nửa ngân sách cho 15 feed và Mongo.
#
# Con số này canh THỜI GIAN, không canh quota. Quota ngày do
# `RedisDailyBudget` đếm thật (xem `adapters/llm/gemini.GENERATE_DAILY_LIMIT`),
# nên đừng suy nó ra từ "trần ngày chia số lượt cron" nữa: phép nhân ấy phụ
# thuộc lịch cron ở `jobs/worker.py` và đã sai hai lần trong ngày 2026-09-15.
#
# Phần dôi ra để lượt sau; cron chạy mỗi 15 phút nên ở trạng thái ổn định nó bắt
# kịp, và `deferred` trong tally cho thấy ngay khi không bắt kịp nữa.
MAX_LLM_CALLS_PER_RUN = 10

# Bao nhiêu lượt liên tiếp kéo được 0 bài thì kêu to (ERROR thay vì WARNING).
#
# Cron chạy mỗi 15 phút nên 4 là đúng MỘT GIỜ câm. Đủ dài để bỏ qua một lần
# trục trặc mạng hay một lần feed bảo trì, đủ ngắn để không mất cả ngày tin.
#
# Con số này có vì hai nguồn đã câm mà không ai thấy trong ngày 2026-09-15:
# GameK nhiều ngày, PCGamesN vài giờ (403 vì thiếu User-Agent). Cả hai lượt
# crawl đều báo `sources: 15, fetched: 644` và trông hoàn toàn khoẻ mạnh — một
# nguồn tụt xuống 0 không làm tổng bằng 0, nó chỉ biến mất khỏi một con số lớn.
EMPTY_STREAK_ALERT = 4

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

    api_key = settings.gemini_api_key.get_secret_value()
    # Không key thì không có lời gọi nào để mà giãn nhịp, nên không dựng bucket.
    # `RedisTokenBucket.__init__` gọi `register_script` ngay lúc khởi tạo, tức
    # là nó ĐÒI một Redis thật kể cả khi sẽ chẳng bao giờ được dùng tới.
    gemini = GeminiAdapter(
        ctx["clients"].http,
        api_key,
        RedisTokenBucket(ctx["clients"].redis, "gemini_generate", GENERATE_RATE)
        if api_key
        else None,
        # Không đặt sàn: job này là bên được ưu tiên của hạn mức ngày, sàn nằm
        # bên `backfill_summaries`.
        RedisDailyBudget(ctx["clients"].redis, "gemini_generate", GENERATE_DAILY_LIMIT)
        if api_key
        else None,
    )
    if not gemini.configured:
        # Vẫn chạy: crawl và gắn entity ở tầng 1-2 không cần LLM. Nhưng phải
        # báo to, vì bản tin sẽ ra feed dưới dạng tiếng Anh chưa tóm tắt và
        # người vận hành cần biết vì sao.
        logger.warning("GEMINI_API_KEY chưa cấu hình: bỏ qua bước tóm tắt và dịch")

    now = dt.datetime.now(dt.UTC)
    seen_hashes = await _recent_hashes(db, now)

    tally = {
        "sources": 0,
        # Nguồn kéo được 0 bài trong lượt này. Khác 0 là có nguồn đang câm —
        # thứ mà `sources` và `fetched` đều không nói được, vì cả hai vẫn trông
        # y hệt lúc khoẻ.
        "sources_empty": 0,
        "fetched": 0,
        "duplicate": 0,
        "already_seen": 0,
        "stored": 0,
        "exact": 0,
        "alias": 0,
        "llm_alias": 0,
        "embedding": 0,
        "manual": 0,
        "summarized": 0,
        # Bài của nguồn tiếng Việt, được lưu mà không tốn lời gọi LLM nào. Tách
        # khỏi `summarized` để đọc được `stored - summarized` là do tiết kiệm có
        # chủ ý hay do một thứ gì đó đang hỏng.
        "vi_skipped": 0,
        # Bài phải để lại cho lượt sau vì hết trần LLM của lượt này. Nằm trong
        # tally chứ không chỉ trong log: nếu con số này luôn khác 0 thì hệ thống
        # đang tụt lại so với lượng tin về, và đó là thứ phải thấy được.
        "deferred": 0,
    }
    llm_calls = 0

    # Nguồn lâu chưa crawl nhất đi trước. Không có `sort` này thì thứ tự luôn
    # cố định, nên mỗi lần chạm trần LLM là **đúng những nguồn cuối bảng** bị
    # bỏ lại — lần nào cũng thế, và tin của họ già đi rồi rụng khỏi feed trước
    # khi tới lượt. Mongo xếp null lên đầu, nên nguồn chưa crawl bao giờ đi đầu.
    #
    # `sort` một mình KHÔNG đủ, và suốt một thời gian dài nó không chạy: mốc
    # `last_crawled_at` trước đây được dập cho mọi nguồn ở cuối vòng lặp, kể cả
    # nguồn vừa bị bỏ lại trắng vì hết trần LLM. Mà cả 15 nguồn đều được dập
    # trong cùng một lượt, theo đúng thứ tự vừa duyệt — nên lượt sau sort ra y
    # hệt thứ tự cũ. Thứ tự bị ĐÓNG BĂNG, đúng cái mà `sort` sinh ra để phá.
    #
    # Đo 2026-09-15: cả 15 nguồn mang mốc trong khoảng 13:15:14-13:16:58, và
    # `GameK — PC/Console` — nguồn cuối bảng — có **0 bài** trong kho sau nhiều
    # ngày chạy, trong khi 14 nguồn còn lại có 16-134 bài.
    #
    # Nên mốc chỉ được dập khi nguồn đã phục vụ XONG (xem cuối vòng lặp).
    async for source_doc in db.sources.find({"status": "active"}).sort("last_crawled_at", 1):
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
        articles = await crawl_rss(source, ctx["clients"].http)
        tally["fetched"] += len(articles)

        # Nguồn câm phải lộ ra ở đây, vì không chỗ nào khác lộ: job vẫn xanh,
        # `sources` vẫn đủ 15, và `fetched` vẫn hàng trăm.
        streak = await ghi_nhan_so_bai(db, source_id, len(articles))
        if streak:
            tally["sources_empty"] += 1
            ghi = logger.error if streak >= EMPTY_STREAK_ALERT else logger.warning
            ghi(
                "nguồn không kéo được bài nào",
                extra={"source": source.name, "url": source.url, "streak": streak},
            )
        # Bài của RIÊNG nguồn này phải để lại. Quyết định có dập mốc hay không
        # nằm ở đây, nên không dùng được `tally["deferred"]` của cả lượt.
        bo_lai = 0

        # Nguồn tiếng Việt không cần dịch, nên không tốn lời gọi LLM nào — mà
        # trần 10 bài/lượt đang là tài nguyên khan hiếm nhất của Phase 6.
        #
        # ĐÁNH ĐỔI phải biết, vì nó không lộ ra ở đâu khác: bài của nguồn này
        # sẽ **không có `summary_vi`**, chỉ có tiêu đề gốc và link. Không lấy
        # luôn phần mô tả trong RSS làm tóm tắt được — `CLAUDE.md` yêu cầu tóm
        # tắt phải là **tự viết**, chép nguyên văn là tái bản nội dung có bản
        # quyền. Muốn có tóm tắt cho nhóm này thì phải trả bằng một lời gọi LLM,
        # đúng cái vừa bỏ đi.
        #
        # Mất thêm `suggested_alias`, nên nhóm này chỉ gắn entity được ở tầng 1-2
        # và rơi vào hàng duyệt tay nhiều hơn.
        can_dich = gemini.configured and source.language != "vi"

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

            # LLM chạy TRƯỚC bước gắn entity, và điều đó không làm hoá đơn dài
            # thêm một đồng: bước tóm tắt vốn chạy cho mọi bài được lưu, bất kể
            # gắn được entity hay không. Đổi lại, `suggested_alias` — thứ model
            # vẫn luôn trả về mà trước nay không ai đọc — kịp làm đầu vào cho
            # hai tầng cuối. Nó còn TIẾT KIỆM: tầng cuối chỉ phải sinh vector
            # khi tầng alias của chính cái tên đó cũng trượt.
            if can_dich and llm_calls >= MAX_LLM_CALLS_PER_RUN:
                # Hết trần thì DỪNG HẲN, không lưu bài dạng chưa dịch. Lưu nó
                # nghĩa là bài đó vĩnh viễn không có tiếng Việt: chưa có job nào
                # quay lại tóm tắt bù. Bỏ qua thì lượt sau nhặt lại từ feed, vì
                # `already_seen` tra theo URL mà URL này chưa vào kho.
                tally["deferred"] += 1
                bo_lai += 1
                continue

            if not can_dich and gemini.configured:
                # Nguồn tiếng Việt: không tốn lời gọi nào, nên cũng KHÔNG bao giờ
                # bị hoãn vì hết trần. Đó là toàn bộ điểm của việc bỏ qua.
                tally["vi_skipped"] += 1

            parsed = None
            if can_dich:
                llm_calls += 1
                try:
                    parsed = await gemini.summarize_and_translate(
                        title=article.title, content=article.original_content
                    )
                except AdapterError as exc:
                    # Bài vẫn được lưu, chỉ là chưa có bản tiếng Việt. Vứt cả
                    # bài đi vì một lần gọi LLM hỏng là mất tin thật.
                    logger.warning(
                        "gọi LLM hỏng, lưu bài dạng chưa dịch",
                        extra={"url": article.url, "error": repr(exc)},
                    )
                if parsed is not None:
                    article.translated_title = parsed.translated_title
                    article.summary_vi = parsed.summary_vi
                    tally["summarized"] += 1

            match = await match_entity(
                db,
                article.title,
                article.original_content,
                qdrant_client=ctx["clients"].qdrant,
                gemini=gemini if gemini.configured else None,
                suggested_alias=parsed.suggested_alias if parsed else None,
            )
            article.matching_tier = match.tier if match.matched else "none"
            article.confidence_score = match.confidence
            article.game_id = str(match.game_id) if match.game_id else None
            tally[match.tier if match.matched else "manual"] += 1

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

        # Chỉ dập mốc khi nguồn này đã được phục vụ HẾT. Còn bài bỏ lại mà vẫn
        # dập thì nguồn tụt xuống cuối hàng đúng lúc nó đang nợ việc nhiều nhất,
        # và vòng xoay không bao giờ tới lượt nó nữa.
        #
        # Giữ nguyên mốc thì lượt sau nó sort lên đầu, `already_seen` bỏ qua
        # phần đã lưu, và phần bỏ lại được xử lý trước. Nguồn có feed chết (0
        # bài) vẫn được dập bình thường — không có gì bỏ lại thì không nợ gì.
        if bo_lai == 0:
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
