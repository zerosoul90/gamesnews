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
from pydantic import SecretStr

from app.adapters.llm.gemini import LLMParsedArticle
from app.core.config import get_settings
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


@pytest.fixture(autouse=True)
def khong_co_key_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ép `GEMINI_API_KEY` rỗng cho cả file này.

    `autouse` và không thể bỏ: `FakeClients.http` là `None`, nên nếu adapter
    thấy có key thì nó đi tới `self._http.post` và nổ `AttributeError`. Cả file
    này trước đây xanh **chỉ vì máy dev không có key** — đặt key thật vào `.env`
    là năm test đỏ ngay, dù không dòng code nào của job đổi.

    Điều đáng sợ hơn cái đỏ: nếu `FakeClients` có một http client thật thì test
    sẽ gọi thẳng Gemini qua Internet mỗi lần chạy suite, tiêu quota thật cho
    những bài viết bịa.
    """
    monkeypatch.setattr(get_settings(), "gemini_api_key", SecretStr(""))


@pytest.fixture
def no_network(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Thay `crawl_rss` bằng bản trả về danh sách dựng sẵn."""

    def use(articles: list[NewsArticle]) -> None:
        # Nhận cả client httpx: job truyền client dùng chung vào để `crawl_rss`
        # đặt được trần chờ cho mỗi nguồn (`services/crawler.py`).
        async def fake_crawl(source: Source, http: Any = None) -> list[NewsArticle]:
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
    game = with_aliases(Game(slug=name.lower().replace(" ", "-"), titles=Titles(primary=name)))
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


async def test_bai_khong_gan_duoc_thi_vao_hang_doi_duyet_tay(mongo_db: Db, no_network: Any) -> None:
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


async def test_hai_trang_chep_cua_nhau_thi_danh_dau_trung(mongo_db: Db, no_network: Any) -> None:
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


async def test_thieu_key_gemini_van_chay_chi_la_khong_dich(mongo_db: Db, no_network: Any) -> None:
    """Thiếu LLM làm mất bản tiếng Việt, không được làm mất cả bài."""
    await add_source(mongo_db)
    no_network([article("Tin tiếng Anh", "https://ign.example/5", "nội dung")])

    tally = await news.crawl_all_sources({"clients": FakeClients(mongo_db)})

    assert tally["stored"] == 1
    assert tally["summarized"] == 0

    doc = await mongo_db.articles.find_one({"url": "https://ign.example/5"})
    assert doc is not None
    assert doc["summary_vi"] is None


# --- `suggested_alias` đi từ LLM tới bước gắn entity -----------------------
#
# Đây là một sợi dây, và sợi dây đứt thì không có triệu chứng: tầng 3 chỉ lặng
# lẽ không bao giờ khớp, y như hồi cả Phase 6 "đã xong" mà chưa hàm nào được
# gọi. Nên phải kiểm CHIỀU ĐI, không chỉ kiểm từng đầu.


class FakeGemini:
    """Đủ hình dạng để `crawl_all_sources` dùng, không ra Internet."""

    def __init__(self, alias: str | None) -> None:
        self._alias = alias
        self.configured = True
        self.calls = 0

    async def summarize_and_translate(self, *, title: str, content: str) -> Any:
        self.calls += 1
        return LLMParsedArticle(
            translated_title=f"[vi] {title}",
            summary_vi="tóm tắt",
            suggested_alias=self._alias,
        )


@pytest.fixture
def fake_gemini(monkeypatch: pytest.MonkeyPatch) -> Any:
    def use(alias: str | None) -> FakeGemini:
        fake = FakeGemini(alias)
        monkeypatch.setattr(news, "GeminiAdapter", lambda *a, **kw: fake)
        return fake

    return use


async def test_ten_llm_trich_ra_gan_duoc_entity(
    mongo_db: Db, no_network: Any, fake_gemini: Any
) -> None:
    """Tiêu đề không khớp alias nào, nhưng model đọc ra được tên game."""
    game_id = await add_game(mongo_db, 1245620, "Elden Ring")
    await add_source(mongo_db)
    no_network([article("Hãng phát hành hé lộ bom tấn", "https://ign.example/6", "nội dung")])
    fake_gemini("Elden Ring")

    tally = await news.crawl_all_sources({"clients": FakeClients(mongo_db)})

    assert tally["llm_alias"] == 1
    assert tally["manual"] == 0

    doc = await mongo_db.articles.find_one({"url": "https://ign.example/6"})
    assert doc is not None
    assert doc["game_id"] == str(game_id)
    assert doc["matching_tier"] == "llm_alias"


async def test_het_tran_llm_thi_de_lai_cho_luot_sau_chu_khong_luu_dang_chua_dich(
    mongo_db: Db, no_network: Any, fake_gemini: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bài dôi ra phải **không được lưu**, chứ không phải lưu dạng chưa dịch.

    Lưu nó là để nó vĩnh viễn không có tiếng Việt: chưa có job nào quay lại tóm
    tắt bù. Bỏ qua thì lượt sau nhặt lại từ feed, vì `already_seen` tra theo URL
    mà URL đó chưa vào kho.
    """
    monkeypatch.setattr(news, "MAX_LLM_CALLS_PER_RUN", 2)
    await add_source(mongo_db)
    no_network(
        [article(f"Tin {i}", f"https://ign.example/tran-{i}", f"nội dung {i}") for i in range(5)]
    )
    fake = fake_gemini(None)

    tally = await news.crawl_all_sources({"clients": FakeClients(mongo_db)})

    assert fake.calls == 2, "không được gọi LLM quá trần"
    assert tally["stored"] == 2
    assert tally["deferred"] == 3
    assert await mongo_db.articles.count_documents({}) == 2


async def test_luot_sau_nhat_lai_dung_nhung_bai_bi_de_lai(
    mongo_db: Db, no_network: Any, fake_gemini: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Chốt đi kèm: "để lại cho lượt sau" chỉ đúng nếu lượt sau thật sự nhặt."""
    monkeypatch.setattr(news, "MAX_LLM_CALLS_PER_RUN", 2)
    await add_source(mongo_db)
    no_network(
        [article(f"Tin {i}", f"https://ign.example/lap-{i}", f"nội dung {i}") for i in range(5)]
    )
    fake_gemini(None)

    await news.crawl_all_sources({"clients": FakeClients(mongo_db)})
    lan_hai = await news.crawl_all_sources({"clients": FakeClients(mongo_db)})

    assert lan_hai["already_seen"] == 2, "hai bài lượt trước đã lưu"
    assert lan_hai["stored"] == 2, "hai bài tiếp theo được nhặt lại"
    assert await mongo_db.articles.count_documents({}) == 4


async def test_nguon_lau_chua_crawl_nhat_di_truoc(
    mongo_db: Db, no_network: Any, fake_gemini: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Thứ tự cố định thì mỗi lần chạm trần là ĐÚNG những nguồn cuối bảng bị bỏ
    lại — lần nào cũng thế, và tin của họ rụng khỏi feed trước khi tới lượt."""
    moi = await add_source(mongo_db)
    await mongo_db.sources.update_one({"_id": moi}, {"$set": {"last_crawled_at": "2026-09-13"}})
    cu = await add_source(mongo_db)
    await mongo_db.sources.update_one({"_id": cu}, {"$set": {"last_crawled_at": "2026-01-01"}})
    no_network([])
    fake_gemini(None)

    thu_tu: list[ObjectId] = []

    async def ghi_lai(db: Db, source_id: ObjectId) -> None:
        thu_tu.append(source_id)

    monkeypatch.setattr(news, "update_last_crawled", ghi_lai)

    await news.crawl_all_sources({"clients": FakeClients(mongo_db)})

    assert thu_tu == [cu, moi]


async def test_nguon_tieng_viet_khong_ton_loi_goi_llm(
    mongo_db: Db, no_network: Any, fake_gemini: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nguồn `language: "vi"` đã là tiếng Việt, dịch nó là ném hạn mức đi.

    Và vì không tốn lời gọi nào, bài của nhóm này KHÔNG bao giờ bị hoãn vì hết
    trần — kể cả khi trần đã cạn sạch. Đó là toàn bộ điểm của việc bỏ qua.
    """
    monkeypatch.setattr(news, "MAX_LLM_CALLS_PER_RUN", 0)
    fake = fake_gemini(None)

    await mongo_db.sources.insert_one(
        Source(name="GameK", url="https://gamek.vn/rss", language="vi").to_mongo()
    )
    no_network([article("Tin tiếng Việt", "https://gamek.vn/1", "nội dung tiếng Việt")])

    tally = await news.crawl_all_sources({"clients": FakeClients(mongo_db)})

    assert fake.calls == 0, "không được gọi LLM cho nguồn tiếng Việt"
    assert tally["stored"] == 1, "trần cạn sạch vẫn phải lưu, vì bài này không cần LLM"
    assert tally["deferred"] == 0
    assert tally["vi_skipped"] == 1

    doc = await mongo_db.articles.find_one({"url": "https://gamek.vn/1"})
    assert doc is not None
    assert doc["summary_vi"] is None
    assert doc["translated_title"] is None


async def test_nguon_bi_bo_lai_khong_bi_dap_moc(
    mongo_db: Db, fake_gemini: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hết trần LLM thì nguồn bị bỏ lại phải GIỮ NGUYÊN `last_crawled_at`.

    Dập mốc cho cả nguồn vừa bị bỏ trắng là đẩy nó xuống cuối hàng đúng lúc nó
    đang nợ việc nhiều nhất. Mà cả 15 nguồn đều được dập trong cùng một lượt,
    theo đúng thứ tự vừa duyệt, nên lượt sau sort ra y hệt — thứ tự đóng băng và
    nguồn cuối bảng không bao giờ tới lượt.

    Đo 2026-09-15 trên kho thật: `GameK — PC/Console` nằm cuối, **0 bài** sau
    nhiều ngày chạy, trong khi 14 nguồn còn lại có 16-134 bài.
    """
    monkeypatch.setattr(news, "MAX_LLM_CALLS_PER_RUN", 1)
    fake_gemini(None)

    truoc = await add_source(mongo_db)
    await mongo_db.sources.update_one({"_id": truoc}, {"$set": {"last_crawled_at": "2026-01-01"}})
    sau = await add_source(mongo_db)
    await mongo_db.sources.update_one({"_id": sau}, {"$set": {"last_crawled_at": "2026-01-02"}})

    # Mỗi nguồn một bài khác URL, nếu không bài của nguồn thứ hai bị tính là
    # `already_seen` và chẳng còn gì để bỏ lại.
    async def crawl_theo_nguon(source: Source, http: Any = None) -> list[NewsArticle]:
        stt = len(da_crawl)
        da_crawl.append(source)
        return [article(f"Tin {stt}", f"https://vi.du/{stt}", f"Noi dung so {stt}")]

    da_crawl: list[Source] = []
    monkeypatch.setattr(news, "crawl_rss", crawl_theo_nguon)

    dap_moc: list[ObjectId] = []

    async def ghi_lai(db: Db, source_id: ObjectId) -> None:
        dap_moc.append(source_id)

    monkeypatch.setattr(news, "update_last_crawled", ghi_lai)

    tally = await news.crawl_all_sources({"clients": FakeClients(mongo_db)})

    assert tally["stored"] == 1, "trần là 1 lời gọi LLM nên chỉ một bài được lưu"
    assert tally["deferred"] == 1
    # Nguồn được phục vụ thì dập mốc; nguồn bị bỏ lại thì KHÔNG, để lượt sau nó
    # sort lên đầu.
    assert dap_moc == [truoc]


async def test_van_tom_tat_ca_khi_da_gan_duoc_o_tang_1(
    mongo_db: Db, no_network: Any, fake_gemini: Any
) -> None:
    """Đảo thứ tự hai bước KHÔNG được làm mất bản dịch của bài đã khớp sớm.

    Và cũng không được gọi LLM thêm lần nào: bước tóm tắt vốn chạy cho mọi bài
    được lưu, đó chính là lý do đổi chỗ nó không tốn thêm đồng nào.
    """
    await add_game(mongo_db, 1245620, "Elden Ring")
    await add_source(mongo_db)
    no_network(
        [
            article(
                "Tin",
                "https://ign.example/7",
                "https://store.steampowered.com/app/1245620/",
            )
        ]
    )
    fake = fake_gemini(None)

    tally = await news.crawl_all_sources({"clients": FakeClients(mongo_db)})

    assert tally["exact"] == 1
    assert tally["summarized"] == 1
    assert fake.calls == 1

    doc = await mongo_db.articles.find_one({"url": "https://ign.example/7"})
    assert doc is not None
    assert doc["summary_vi"] == "tóm tắt"


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
