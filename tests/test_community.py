"""Điểm cộng đồng — `app/services/community.py`, `app/api/community.py`.

`PHASE-8.md` quy định ẩn điểm dưới 20 lượt để chống review bombing. Bản trước
"ẩn" bằng cách gửi kèm cờ `is_hidden: true` **cạnh con số** — điểm bị giấu trên
giao diện nhưng nằm nguyên trong payload, ai mở tab Network cũng đọc được.
"""

from __future__ import annotations

from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.community import UserReview
from app.services.community import (
    MIN_REVIEWS_TO_SHOW,
    award_badge,
    calculate_game_score,
    reviews_of_game,
)

Db = AsyncIOMotorDatabase[dict[str, Any]]


async def add_reviews(db: Db, game_id: ObjectId, scores: list[int]) -> None:
    await db.user_reviews.insert_many(
        [{"user_id": ObjectId(), "game_id": game_id, "score": score} for score in scores]
    )


async def test_duoi_nguong_thi_khong_co_diem_trong_payload(mongo_db: Db) -> None:
    game_id = ObjectId()
    await add_reviews(mongo_db, game_id, [10] * (MIN_REVIEWS_TO_SHOW - 1))

    result = await calculate_game_score(mongo_db, str(game_id))

    assert result is not None
    assert result["is_hidden"] is True
    assert result["average_score"] is None  # <- chốt chính
    assert result["review_count"] == MIN_REVIEWS_TO_SHOW - 1


async def test_du_nguong_thi_hien_diem(mongo_db: Db) -> None:
    game_id = ObjectId()
    await add_reviews(mongo_db, game_id, [8] * MIN_REVIEWS_TO_SHOW)

    result = await calculate_game_score(mongo_db, str(game_id))

    assert result is not None
    assert result["is_hidden"] is False
    assert result["average_score"] == 8.0


async def test_chua_co_review_nao(mongo_db: Db) -> None:
    result = await calculate_game_score(mongo_db, str(ObjectId()))

    assert result is not None
    assert result["review_count"] == 0
    assert result["average_score"] is None


async def test_trao_badge_dung_mot_lan(mongo_db: Db) -> None:
    user_id = str(ObjectId())

    assert await award_badge(mongo_db, user_id, "reviewer") is True
    assert await award_badge(mongo_db, user_id, "reviewer") is False
    assert await mongo_db.user_badges.count_documents({"badge_type": "reviewer"}) == 1


# --- danh sách đánh giá ------------------------------------------------------


async def test_danh_sach_danh_gia_khong_bi_nguong_20_chan(mongo_db: Db) -> None:
    """Ngưỡng `MIN_REVIEWS_TO_SHOW` chỉ áp cho ĐIỂM TRUNG BÌNH, không áp cho
    danh sách. Hai thứ khác nhau: ngưỡng tồn tại để vài người không dìm được một
    con số thống kê, còn từng bài là ý kiến của một người — giấu đi thì người
    vừa viết thấy bài mình biến mất và họ viết lại."""
    game_id = ObjectId()
    for i in range(3):
        await mongo_db.user_reviews.insert_one(
            UserReview(user_id=ObjectId(), game_id=game_id, score=8, comment=f"hay {i}").to_mongo()
        )

    reviews, total = await reviews_of_game(mongo_db, str(game_id))
    diem = await calculate_game_score(mongo_db, str(game_id))

    assert total == 3, "danh sách phải hiện đủ dù dưới ngưỡng"
    assert len(reviews) == 3
    # Trong khi điểm trung bình vẫn ẩn.
    assert diem is not None
    assert diem["is_hidden"] is True
    assert diem["average_score"] is None


async def test_danh_gia_moi_nhat_truoc(mongo_db: Db) -> None:
    game_id = ObjectId()
    for moc in ("2026-09-10T00:00:00+00:00", "2026-09-17T00:00:00+00:00"):
        doc = UserReview(user_id=ObjectId(), game_id=game_id, score=7).to_mongo()
        doc["created_at"] = moc
        await mongo_db.user_reviews.insert_one(doc)

    reviews, _ = await reviews_of_game(mongo_db, str(game_id))

    assert reviews[0]["created_at"] > reviews[1]["created_at"]


async def test_game_id_sai_dang_tra_rong_chu_khong_no(mongo_db: Db) -> None:
    assert await reviews_of_game(mongo_db, "khong-phai-objectid") == ([], 0)


async def test_chi_tra_danh_gia_cua_dung_game(mongo_db: Db) -> None:
    game_a, game_b = ObjectId(), ObjectId()
    await mongo_db.user_reviews.insert_one(
        UserReview(user_id=ObjectId(), game_id=game_a, score=9).to_mongo()
    )
    await mongo_db.user_reviews.insert_one(
        UserReview(user_id=ObjectId(), game_id=game_b, score=3).to_mongo()
    )

    _, total = await reviews_of_game(mongo_db, str(game_a))

    assert total == 1
