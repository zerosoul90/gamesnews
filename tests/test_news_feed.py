"""Feed tin công khai — `app/services/news_feed.py`.

Trước lượt này kho `articles` không có đường ra nào: 600 bài đã dịch nằm trong
Mongo mà không API hay trang nào đọc được. Trọng tâm của file này là hai thứ dễ
hỏng im lặng — ràng buộc bản quyền, và hai phép join đổi kiểu.
"""

from __future__ import annotations

from typing import Any

import pytest
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.services.news_feed import public_feed

Db = AsyncIOMotorDatabase[dict[str, Any]]

NGUYEN_VAN = "<section>Nguyên văn bài gốc, KHÔNG được tái bản.</section>"


async def add_source(db: Db, name: str, language: str = "en") -> ObjectId:
    res = await db.sources.insert_one({"name": name, "language": language})
    return ObjectId(res.inserted_id)


async def add_article(
    db: Db,
    *,
    source_id: ObjectId,
    title: str = "Original Title",
    summary_vi: str | None = "Tóm tắt tiếng Việt.",
    published_at: str = "2026-09-11T18:28:49+00:00",
    status: str = "pending",
    game_id: str | None = None,
    translated_title: str | None = "Tiêu đề đã dịch",
) -> ObjectId:
    """Bài lưu `source_id`/`game_id` dạng CHUỖI — đúng như job thật ghi."""
    doc: dict[str, Any] = {
        "source_id": str(source_id),
        "url": "https://example.com/bai-viet",
        "title": title,
        "original_content": NGUYEN_VAN,
        "simhash": "1",
        "status": status,
        "translated_title": translated_title,
        "summary_vi": summary_vi,
        "published_at": published_at,
        "game_id": game_id,
    }
    res = await db.articles.insert_one(doc)
    return ObjectId(res.inserted_id)


async def test_khong_bao_gio_tra_nguyen_van_bai_goc(mongo_db: Db) -> None:
    """Ràng buộc cứng của `CLAUDE.md`: không tái bản nguyên văn nội dung có bản
    quyền. `original_content` giữ HTML đầy đủ của bài gốc, nên nó không được ra
    khỏi tầng service dưới bất kỳ tên nào."""
    src = await add_source(mongo_db, "IGN")
    await add_article(mongo_db, source_id=src)

    articles, _ = await public_feed(mongo_db)

    assert len(articles) == 1
    phang = str(articles[0])
    assert "original_content" not in articles[0]
    assert NGUYEN_VAN not in phang
    assert "Nguyên văn" not in phang


async def test_bai_chua_co_tom_tat_khong_len_feed(mongo_db: Db) -> None:
    """Mốc lên feed là `summary_vi`, không phải `status`. Bài chưa dịch mà lên
    feed thì trang chỉ còn tiêu đề tiếng Anh và một cái link — tức đúng thứ
    ràng buộc bản quyền không cho làm."""
    src = await add_source(mongo_db, "IGN")
    await add_article(mongo_db, source_id=src, summary_vi=None)
    await add_article(mongo_db, source_id=src, summary_vi="")

    articles, total = await public_feed(mongo_db)

    assert articles == []
    assert total == 0


async def test_bai_pending_van_len_feed(mongo_db: Db) -> None:
    """Chốt quyết định đã chọn: `status` mặc định là `pending` và KHÔNG có bước
    nào nâng nó lên `published`. Lọc theo `published` thì feed rỗng tuyệt đối."""
    src = await add_source(mongo_db, "IGN")
    await add_article(mongo_db, source_id=src, status="pending")

    articles, total = await public_feed(mongo_db)

    assert total == 1
    assert articles[0]["summary"] == "Tóm tắt tiếng Việt."


async def test_bai_trung_bi_loai(mongo_db: Db) -> None:
    src = await add_source(mongo_db, "IGN")
    await add_article(mongo_db, source_id=src, status="duplicate")

    articles, total = await public_feed(mongo_db)

    assert articles == []
    assert total == 0


async def test_gan_nguon_qua_phep_doi_kieu(mongo_db: Db) -> None:
    """`articles.source_id` là CHUỖI còn `sources._id` là `ObjectId`. Join thẳng
    hai thứ đó trả rỗng mà không báo lỗi — bẫy đã làm một phép đếm trong phiên
    này ra 0 một cách vô nghĩa."""
    src = await add_source(mongo_db, "PC Gamer", language="en")
    await add_article(mongo_db, source_id=src)

    articles, _ = await public_feed(mongo_db)

    assert articles[0]["source"] == {"name": "PC Gamer", "language": "en"}


async def test_gan_game_qua_phep_doi_kieu(mongo_db: Db) -> None:
    src = await add_source(mongo_db, "IGN")
    game = await mongo_db.games.insert_one(
        {
            "slug": "elden-ring",
            "titles": {"primary": "Elden Ring", "vi": "Vòng Nguyệt Quế"},
            "media": {"cover": "https://img/cover.jpg"},
        }
    )
    await add_article(mongo_db, source_id=src, game_id=str(game.inserted_id))

    articles, _ = await public_feed(mongo_db)

    assert articles[0]["game"] == {
        # Tên tiếng Việt trước, như `/deals`.
        "title": "Vòng Nguyệt Quế",
        "slug": "elden-ring",
        "cover_image_url": "https://img/cover.jpg",
    }


async def test_bai_khong_gan_duoc_game_van_len_feed(mongo_db: Db) -> None:
    """Chỉ 86/600 bài gắn được game. Nếu thiếu game mà bị loại thì feed mất 86%
    nội dung của chính nó."""
    src = await add_source(mongo_db, "IGN")
    await add_article(mongo_db, source_id=src, game_id=None)

    articles, total = await public_feed(mongo_db)

    assert total == 1
    assert articles[0]["game"] is None


async def test_moi_nhat_truoc(mongo_db: Db) -> None:
    """Hai định dạng `published_at` cùng tồn tại trong kho thật: có và không có
    phần micro giây. Cả hai đều kết thúc `+00:00` nên sắp theo chuỗi vẫn đúng
    thứ tự thời gian."""
    src = await add_source(mongo_db, "IGN")
    await add_article(mongo_db, source_id=src, published_at="2026-09-11T18:28:49+00:00")
    await add_article(
        mongo_db, source_id=src, published_at="2026-09-15T13:45:07.172767+00:00"
    )
    await add_article(mongo_db, source_id=src, published_at="2026-09-13T06:00:00+00:00")

    articles, _ = await public_feed(mongo_db)

    moc = [a["published_at"] for a in articles]
    assert moc == sorted(moc, reverse=True)


async def test_tieu_de_goc_la_duong_lui(mongo_db: Db) -> None:
    """Bài có tóm tắt tiếng Việt mà thiếu tiêu đề dịch vẫn đọc được — đừng để
    thẻ tin trống tiêu đề."""
    src = await add_source(mongo_db, "IGN")
    await add_article(mongo_db, source_id=src, translated_title=None, title="Fallback")

    articles, _ = await public_feed(mongo_db)

    assert articles[0]["title"] == "Fallback"


async def test_phan_trang_va_tong_so_dem_cung_mot_dieu_kien(mongo_db: Db) -> None:
    """`total` và danh sách phải dùng chung bộ lọc. Lệch nhau thì nút "xem thêm"
    sai theo cách rất khó thấy."""
    src = await add_source(mongo_db, "IGN")
    for i in range(5):
        await add_article(mongo_db, source_id=src, published_at=f"2026-09-1{i}T00:00:00+00:00")
    # Một bài chưa dịch: phải vắng mặt ở CẢ hai vế.
    await add_article(mongo_db, source_id=src, summary_vi=None)

    trang1, total = await public_feed(mongo_db, limit=2, offset=0)
    trang2, total2 = await public_feed(mongo_db, limit=2, offset=2)

    assert total == 5
    assert total2 == 5
    assert len(trang1) == 2
    assert len(trang2) == 2
    assert {a["id"] for a in trang1}.isdisjoint({a["id"] for a in trang2})


async def test_loc_theo_game(mongo_db: Db) -> None:
    src = await add_source(mongo_db, "IGN")
    gid = str(ObjectId())
    await add_article(mongo_db, source_id=src, game_id=gid)
    await add_article(mongo_db, source_id=src, game_id=None)

    articles, total = await public_feed(mongo_db, game_id=gid)

    assert total == 1
    assert len(articles) == 1


@pytest.mark.parametrize("limit,mong_doi", [(0, 1), (999, 50)])
async def test_limit_bi_kep_trong_khoang_an_toan(
    mongo_db: Db, limit: int, mong_doi: int
) -> None:
    """Service tự kẹp chứ không tin người gọi: router có `Query(le=50)` nhưng
    service còn được gọi từ chỗ khác."""
    src = await add_source(mongo_db, "IGN")
    for i in range(3):
        await add_article(mongo_db, source_id=src, published_at=f"2026-09-0{i}T00:00:00+00:00")

    articles, _ = await public_feed(mongo_db, limit=limit)

    assert len(articles) <= mong_doi
    assert len(articles) >= 1
