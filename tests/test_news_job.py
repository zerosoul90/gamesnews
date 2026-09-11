"""Job crawl tin — `app/jobs/news.py`.

Job này trước đây **không tồn tại**. Mọi mảnh của Phase 6 đã có sẵn
(`crawl_rss`, `dedup`, `entity_matcher`, `entity_review`) nhưng không sợi dây
nào nối chúng, và `WorkerSettings.functions` không có job tin nào — nên chưa
từng có một bài viết nào đi vào `articles`.

Không gọi ra Internet: `crawl_rss` được thay bằng bản trả fixture. Thứ đáng
kiểm ở đây là **thứ tự các bước** và **cái gì được ghi xuống**, không phải khả
năng parse RSS của `feedparser`.
"""

from __future__ import annotations

import datetime as dt
import json
from typing import Any

import pytest
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.jobs import news
from app.models.article import NewsArticle
from app.models.game import Game, Titles
from app.models.source import Source, SourceStatus
from app.services import sources
from app.services.catalog import upsert_game, with_aliases
from app.services.dedup import compute_simhash

Db = AsyncIOMotorDatabase[dict[str, Any]]


class FakeClients:
    """Đủ hình dạng để job chạy: `.db`, `.http`, `.qdrant`."""

    def __init__(self, db: Db) -> None:
        self.db = db
        self.http = None
        self.qdrant = None


def article(title: str, url: str, content: str) -> NewsArticle:
    now = dt.datetime.now(dt.UTC).isoformat()
    return NewsArticle(
        source_id="tạm",
        url=url,
        title=title,
        original_content=content,
        simhash=compute_simhash(content),
        published_at=now,
        created_at=now,
    )


@pytest.fixture
def no_network(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Thay `crawl_rss` bằng bản trả về danh sách dựng sẵn."""

    def use(articles: list[NewsArticle]) -> None:
        async def fake_crawl(source: Source) -> list[NewsArticle]:
            return articles

        monkeypatch.setattr(news, "crawl_rss", fake_crawl)

    return use


async def add_source(db: Db, *, status: SourceStatus = "active") -> ObjectId:
    result = await db.sources.insert_one(
        Source(name="IGN", url="https://example.invalid/rss", status=status).to_mongo()
    )
    inserted: ObjectId = result.inserted_id
    return inserted


async def add_game(db: Db, appid: int, name: str) -> ObjectId:
    game = with_aliases(
        Game(slug=name.lower().replace(" ", "-"), titles=Titles(primary=name))
    )
    game.external_ids.steam_appid = appid
    await upsert_game(db, game, key="steam_appid")
    doc = await db.games.find_one({"external_ids.steam_appid": appid})
    assert doc is not None
    game_id: ObjectId = doc["_id"]
    return game_id


async def test_ghi_bai_va_gan_entity_qua_link_store(mongo_db: Db, no_network: Any) -> None:
    source_id = await add_source(mongo_db)
    game_id = await add_game(mongo_db, 1245620, "ELDEN RING")

    no_network(
        [
            article(
                "Elden Ring giảm giá sâu",
                "https://ign.example/1",
                'Xem tại <a href="https://store.steampowered.com/app/1245620/">Steam</a>',
            )
        ]
    )

    tally = await news.crawl_all_sources({"clients": FakeClients(mongo_db)})

    assert tally["stored"] == 1
    assert tally["exact"] == 1

    doc = await mongo_db.articles.find_one({"url": "https://ign.example/1"})
    assert doc is not None
    assert doc["game_id"] == str(game_id)
    assert doc["matching_tier"] == "exact"
    # Nguồn phải là _id thật, không phải tên: tên nguồn đổi được.
    assert doc["source_id"] == str(source_id)


async def test_bai_khong_gan_duoc_thi_vao_hang_doi_duyet_tay(
    mongo_db: Db, no_network: Any
) -> None:
    await add_source(mongo_db)
    no_network([article("Tin về một hãng phần cứng", "https://ign.example/2", "không có gì")])

    tally = await news.crawl_all_sources({"clients": FakeClients(mongo_db)})

    assert tally["manual"] == 1
    assert await mongo_db.entity_review_queue.count_documents({"status": "pending"}) == 1


async def test_chay_lai_khong_ghi_trung_bai(mongo_db: Db, no_network: Any) -> None:
    """Index unique trên `url` là chốt chống trùng rẻ nhất, và nó phải có thật."""
    await add_source(mongo_db)
    no_network([article("Tin A", "https://ign.example/3", "nội dung A")])

    first = await news.crawl_all_sources({"clients": FakeClients(mongo_db)})
    second = await news.crawl_all_sources({"clients": FakeClients(mongo_db)})

    assert first["stored"] == 1
    assert second["stored"] == 0
    assert second["already_seen"] == 1
    assert await mongo_db.articles.count_documents({}) == 1


async def test_hai_trang_chep_cua_nhau_thi_danh_dau_trung(
    mongo_db: Db, no_network: Any
) -> None:
    await add_source(mongo_db)
    body = "Bom tấn mới lộ ngày ra mắt chính thức vào tháng sau, kèm bản mở rộng lớn."
    no_network(
        [
            article("Bản gốc", "https://a.example/x", body),
            article("Bản chép lại", "https://b.example/x", body),
        ]
    )

    tally = await news.crawl_all_sources({"clients": FakeClients(mongo_db)})

    assert tally["stored"] == 1
    assert tally["duplicate"] == 1

    copied = await mongo_db.articles.find_one({"url": "https://b.example/x"})
    assert copied is not None
    assert copied["status"] == "duplicate"


async def test_nguon_tat_thi_khong_crawl(mongo_db: Db, no_network: Any) -> None:
    await add_source(mongo_db, status="inactive")
    no_network([article("Tin", "https://ign.example/4", "nội dung")])

    tally = await news.crawl_all_sources({"clients": FakeClients(mongo_db)})

    assert tally["sources"] == 0
    assert tally["stored"] == 0


async def test_ghi_lai_moc_da_crawl(mongo_db: Db, no_network: Any) -> None:
    """`update_last_crawled` có sẵn từ lâu mà chưa chỗ nào gọi."""
    source_id = await add_source(mongo_db)
    no_network([])

    await news.crawl_all_sources({"clients": FakeClients(mongo_db)})

    doc = await mongo_db.sources.find_one({"_id": source_id})
    assert doc is not None
    assert doc["last_crawled_at"] is not None


async def test_thieu_key_gemini_van_chay_chi_la_khong_dich(
    mongo_db: Db, no_network: Any
) -> None:
    """Thiếu LLM làm mất bản tiếng Việt, không được làm mất cả bài."""
    await add_source(mongo_db)
    no_network([article("Tin tiếng Anh", "https://ign.example/5", "nội dung")])

    tally = await news.crawl_all_sources({"clients": FakeClients(mongo_db)})

    assert tally["stored"] == 1
    assert tally["summarized"] == 0

    doc = await mongo_db.articles.find_one({"url": "https://ign.example/5"})
    assert doc is not None
    assert doc["summary_vi"] is None


# --- Mồi danh sách nguồn ---------------------------------------------------
#
# Job trên chạy đúng từ lâu rồi. Thứ thiếu là dữ liệu: `sources` rỗng, nên mỗi
# 15 phút job trả `sources: 0` và Phase 6 đứng im trong khi `PROGRESS.md` ghi
# là đã xong.


def test_danh_sach_nguon_moi_dung_luoc_do() -> None:
    """Một dấu phẩy sai trong JSON phải đỏ ở đây, đừng đợi tới lúc khởi động."""
    raw = json.loads(sources.SEED_FILE.read_text(encoding="utf-8"))

    parsed = [Source(**entry) for entry in raw]

    assert len(parsed) >= 10, "PHASE-6 yêu cầu bắt đầu với 10-15 nguồn"
    assert len(parsed) <= 15
    assert {s.language for s in parsed} == {"en", "vi"}, "phải có cả hai ngôn ngữ"
    assert len({s.url for s in parsed}) == len(parsed), "URL trùng thì crawl hai lần một nguồn"
    assert all(s.status == "active" for s in parsed)


async def test_moi_nguon_khi_collection_rong(mongo_db: Db) -> None:
    added = await sources.seed_default_sources(mongo_db)

    assert added >= 10
    assert await mongo_db.sources.count_documents({}) == added


async def test_khong_moi_de_len_lua_chon_cua_admin(mongo_db: Db) -> None:
    """Admin tắt hoặc xoá một nguồn thì lần khởi động sau không được dựng lại."""
    await add_source(mongo_db, status="inactive")

    added = await sources.seed_default_sources(mongo_db)

    assert added == 0
    assert await mongo_db.sources.count_documents({}) == 1
