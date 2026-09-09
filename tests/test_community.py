"""Điểm cộng đồng — `app/services/community.py`, `app/api/community.py`.

`PHASE-8.md` quy định ẩn điểm dưới 20 lượt để chống review bombing. Bản trước
"ẩn" bằng cách gửi kèm cờ `is_hidden: true` **cạnh con số** — điểm bị giấu trên
giao diện nhưng nằm nguyên trong payload, ai mở tab Network cũng đọc được.
"""

from __future__ import annotations

from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.services.community import MIN_REVIEWS_TO_SHOW, award_badge, calculate_game_score

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
