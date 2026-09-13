"""Tóm tắt bù — `app/jobs/summaries.py`.

819/843 bài trong kho không có `summary_vi`: chúng vào kho trong những ngày
`GEMINI_API_KEY` còn trống, và `crawl_all_sources` chỉ dịch bài **ngay lúc ghi
nó xuống**. Không có job này thì chúng nằm đó vĩnh viễn dưới dạng tiêu đề tiếng
Anh — mà `PHASE-6.md` gọi việc đưa tin sang tiếng Việt là giá trị lõi của phase.

Thứ đáng kiểm ở đây là **tiêu hạn mức vào đúng chỗ**: bỏ bài trùng, bài mới
trước, và dừng đúng lúc thay vì hỏng thêm 24 lần nữa.
"""

from __future__ import annotations

from typing import Any

import pytest
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import SecretStr

from app.adapters.base import RateLimitedError
from app.adapters.llm.gemini import LLMParsedArticle
from app.core.config import get_settings
from app.jobs import summaries
from app.models.article import ArticleStatus
from app.models.game import ExternalIds, Game, Titles
from app.services import entity_review
from app.services.catalog import ensure_indexes, games, upsert_game, with_aliases

Db = AsyncIOMotorDatabase[dict[str, Any]]


class FakeClients:
    def __init__(self, db: Db) -> None:
        self.db = db
        self.http = None
        self.qdrant = None
        self.redis = None


class FakeGemini:
    """Trả về bản dịch dựng sẵn, hoặc ném lỗi ở lời gọi thứ `no_o_lan`."""

    def __init__(self, alias: str | None = None, *, no_o_lan: int | None = None) -> None:
        self._alias = alias
        self._no_o_lan = no_o_lan
        self.configured = True
        self.titles: list[str] = []

    async def summarize_and_translate(self, *, title: str, content: str) -> Any:
        self.titles.append(title)
        if self._no_o_lan is not None and len(self.titles) >= self._no_o_lan:
            raise RateLimitedError("hết hạn mức")
        return LLMParsedArticle(
            translated_title=f"[vi] {title}",
            summary_vi="tóm tắt tiếng Việt",
            suggested_alias=self._alias,
        )


@pytest.fixture(autouse=True)
def co_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Job thoát sớm khi thiếu key, nên mọi test dưới đây cần một key giả."""
    monkeypatch.setattr(get_settings(), "gemini_api_key", SecretStr("khoa-gia"))


@pytest.fixture
def fake_gemini(monkeypatch: pytest.MonkeyPatch) -> Any:
    def use(alias: str | None = None, *, no_o_lan: int | None = None) -> FakeGemini:
        fake = FakeGemini(alias, no_o_lan=no_o_lan)
        monkeypatch.setattr(summaries, "GeminiAdapter", lambda *a, **kw: fake)
        # `RedisTokenBucket` đòi Redis thật ngay lúc khởi tạo.
        monkeypatch.setattr(summaries, "RedisTokenBucket", lambda *a, **kw: None)
        return fake

    return use


async def add_article(
    db: Db,
    *,
    title: str,
    url: str,
    published_at: str = "2026-09-13T00:00:00+00:00",
    summary_vi: str | None = None,
    status: ArticleStatus = "pending",
    game_id: str | None = None,
) -> ObjectId:
    result = await db.articles.insert_one(
        {
            "source_id": "tạm",
            "url": url,
            "title": title,
            "original_content": "nội dung",
            "simhash": "0",
            "status": status,
            "game_id": game_id,
            "matching_tier": "none",
            "confidence_score": 0.0,
            "summary_vi": summary_vi,
            "translated_title": None,
            "published_at": published_at,
        }
    )
    inserted: ObjectId = result.inserted_id
    return inserted


async def add_game(db: Db, name: str) -> ObjectId:
    await ensure_indexes(db)
    await upsert_game(
        db,
        with_aliases(
            Game(
                slug=name.lower().replace(" ", "-"),
                titles=Titles(primary=name),
                external_ids=ExternalIds(steam_appid=abs(hash(name)) % 10**6),
            )
        ),
        key="steam_appid",
    )
    doc = await games(db).find_one({"titles.primary": name})
    assert doc is not None
    game_id: ObjectId = doc["_id"]
    return game_id


async def test_dich_bai_thieu_tieng_viet(mongo_db: Db, fake_gemini: Any) -> None:
    await add_article(mongo_db, title="Elden Ring news", url="https://x/1")
    fake_gemini()

    tally = await summaries.backfill_summaries({"clients": FakeClients(mongo_db)})

    assert tally["summarized"] == 1

    doc = await mongo_db.articles.find_one({"url": "https://x/1"})
    assert doc is not None
    assert doc["summary_vi"] == "tóm tắt tiếng Việt"
    assert doc["translated_title"] == "[vi] Elden Ring news"


async def test_khong_dich_lai_bai_da_co_tieng_viet(mongo_db: Db, fake_gemini: Any) -> None:
    """Mỗi lời gọi là một lần tiêu hạn mức; dịch lại thứ đã dịch là đổ đi."""
    await add_article(mongo_db, title="Đã dịch", url="https://x/2", summary_vi="có rồi")
    fake = fake_gemini()

    tally = await summaries.backfill_summaries({"clients": FakeClients(mongo_db)})

    assert tally["checked"] == 0
    assert fake.titles == []


async def test_bo_qua_bai_trung(mongo_db: Db, fake_gemini: Any) -> None:
    """137/819 bài là bản trùng — chúng không bao giờ hiện ra cho ai đọc."""
    await add_article(mongo_db, title="Bản trùng", url="https://x/3", status="duplicate")
    fake = fake_gemini()

    tally = await summaries.backfill_summaries({"clients": FakeClients(mongo_db)})

    assert tally["checked"] == 0
    assert fake.titles == []


async def test_bai_moi_nhat_duoc_dich_truoc(mongo_db: Db, fake_gemini: Any) -> None:
    """Tin cũ mất giá trị nhanh; hàng tồn không vơi hết cũng không sao."""
    await add_article(
        mongo_db, title="Cũ", url="https://x/cu", published_at="2026-09-01T00:00:00+00:00"
    )
    await add_article(
        mongo_db, title="Mới", url="https://x/moi", published_at="2026-09-13T00:00:00+00:00"
    )
    fake = fake_gemini()

    await summaries.backfill_summaries({"clients": FakeClients(mongo_db)})

    assert fake.titles == ["Mới", "Cũ"]


async def test_het_han_muc_thi_dung_luot_chu_khong_hong_tiep(
    mongo_db: Db, fake_gemini: Any
) -> None:
    """Hỏng thêm 24 lần nữa chỉ ăn thêm quota của job crawl."""
    for i in range(5):
        await add_article(mongo_db, title=f"Tin {i}", url=f"https://x/han-{i}")
    fake = fake_gemini(no_o_lan=3)

    tally = await summaries.backfill_summaries({"clients": FakeClients(mongo_db)})

    assert len(fake.titles) == 3, "phải dừng ngay ở lần hỏng đầu tiên"
    assert tally["summarized"] == 2
    assert tally["failed"] == 1


async def test_luot_sau_chay_tiep_tu_cho_dang_do(mongo_db: Db, fake_gemini: Any) -> None:
    """Mốc nằm trong dữ liệu (`summary_vi` đã điền chưa), không trong tiến trình."""
    for i in range(4):
        await add_article(mongo_db, title=f"Tin {i}", url=f"https://x/tiep-{i}")
    fake_gemini(no_o_lan=3)

    await summaries.backfill_summaries({"clients": FakeClients(mongo_db)})
    assert await mongo_db.articles.count_documents({"summary_vi": None}) == 2

    fake_gemini()
    await summaries.backfill_summaries({"clients": FakeClients(mongo_db)})
    assert await mongo_db.articles.count_documents({"summary_vi": None}) == 0


async def test_gan_lai_entity_bang_ten_llm_trich_ra(mongo_db: Db, fake_gemini: Any) -> None:
    """Cùng một lời gọi đã trả về `suggested_alias`; vứt nó đi là lặp lại đúng
    cái sai vừa sửa — trường đó nằm trong prompt từ đầu mà không ai đọc."""
    game_id = await add_game(mongo_db, "Elden Ring")
    article_id = await add_article(mongo_db, title="Bom tấn ra bản mới", url="https://x/4")
    await entity_review.enqueue(
        mongo_db, article_id=article_id, title="Bom tấn ra bản mới", url="https://x/4"
    )
    fake_gemini("Elden Ring")

    tally = await summaries.backfill_summaries({"clients": FakeClients(mongo_db)})

    assert tally["matched"] == 1

    doc = await mongo_db.articles.find_one({"_id": article_id})
    assert doc is not None
    assert doc["game_id"] == str(game_id)
    assert doc["matching_tier"] == "llm_alias"


async def test_gan_duoc_thi_hang_doi_duyet_ngan_lai(mongo_db: Db, fake_gemini: Any) -> None:
    """Thiếu bước này thì hàng đợi không bao giờ ngắn lại, và người duyệt phải
    nhìn lại đúng bài mà hệ thống đã tự trả lời được."""
    await add_game(mongo_db, "Elden Ring")
    article_id = await add_article(mongo_db, title="Bom tấn ra bản mới", url="https://x/5")
    await entity_review.enqueue(
        mongo_db, article_id=article_id, title="Bom tấn ra bản mới", url="https://x/5"
    )
    fake_gemini("Elden Ring")

    await summaries.backfill_summaries({"clients": FakeClients(mongo_db)})

    row = await entity_review.queue(mongo_db).find_one({"article_id": article_id})
    assert row is not None
    assert row["status"] == "resolved"
    # Phải phân biệt được hàng đợi ngắn lại vì người làm hay vì máy tự nhận.
    assert row["resolved_by"] == "auto"


async def test_may_tu_nhan_thi_khong_day_alias_cho_catalog(mongo_db: Db, fake_gemini: Any) -> None:
    """Alias dạy tầng 2 cho mọi bài về sau. Dạy nó bằng phỏng đoán của máy thì
    một lần sai nhân lên mãi — luật "alias do người duyệt chỉ định" có từ
    2026-09-09 và vẫn đúng."""
    game_id = await add_game(mongo_db, "Elden Ring")
    truoc = await games(mongo_db).find_one({"_id": game_id}, {"aliases": 1})
    assert truoc is not None

    article_id = await add_article(mongo_db, title="Bom tấn ra bản mới", url="https://x/6")
    await entity_review.enqueue(
        mongo_db, article_id=article_id, title="Bom tấn ra bản mới", url="https://x/6"
    )
    fake_gemini("Elden Ring")

    await summaries.backfill_summaries({"clients": FakeClients(mongo_db)})

    sau = await games(mongo_db).find_one({"_id": game_id}, {"aliases": 1})
    assert sau is not None
    assert sau["aliases"] == truoc["aliases"]


async def test_khong_dung_matching_tier_manual(mongo_db: Db, fake_gemini: Any) -> None:
    """`resolve()` đặt tier "manual" — khai rằng có người đã nhìn bài này. Không
    có ai cả, và truy ngược một lần gắn sai sẽ chỉ vào người không tồn tại."""
    await add_game(mongo_db, "Elden Ring")
    article_id = await add_article(mongo_db, title="Bom tấn ra bản mới", url="https://x/7")
    fake_gemini("Elden Ring")

    await summaries.backfill_summaries({"clients": FakeClients(mongo_db)})

    doc = await mongo_db.articles.find_one({"_id": article_id})
    assert doc is not None
    assert doc["matching_tier"] != "manual"


async def test_bai_da_co_entity_thi_khong_gan_lai(mongo_db: Db, fake_gemini: Any) -> None:
    """Dịch bù không được phép đổi entity của bài đã gắn — nhất là bài người đã
    duyệt tay."""
    cu = str(ObjectId())
    article_id = await add_article(mongo_db, title="Tin", url="https://x/8", game_id=cu)
    await add_game(mongo_db, "Elden Ring")
    fake_gemini("Elden Ring")

    tally = await summaries.backfill_summaries({"clients": FakeClients(mongo_db)})

    assert tally["matched"] == 0
    doc = await mongo_db.articles.find_one({"_id": article_id})
    assert doc is not None
    assert doc["game_id"] == cu


async def test_thieu_key_thi_bao_chu_khong_im_lang(
    mongo_db: Db, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "gemini_api_key", SecretStr(""))
    await add_article(mongo_db, title="Tin", url="https://x/9")

    tally = await summaries.backfill_summaries({"clients": FakeClients(mongo_db)})

    assert tally == {"checked": 0, "summarized": 0, "matched": 0, "failed": 0}


def test_san_token_nho_hon_suc_chua_bucket() -> None:
    """`RedisTokenBucket` từ chối `reserve >= capacity`, và nếu lọt thì job chờ
    hết `max_wait_seconds` rồi chết mỗi lượt — hỏng trông như lỗi mạng."""
    from app.adapters.llm.gemini import GENERATE_RATE

    assert 0 < summaries.RESERVE_FOR_CRAWL < GENERATE_RATE.capacity
