from typing import Any

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException

from app.api.auth import get_current_user_id
from app.core.deps import MongoDep
from app.models.community import UserReview
from app.services.community import award_badge, calculate_game_score

router = APIRouter(prefix="/community", tags=["community"])



@router.post("/reviews")
async def post_review(
    review_data: dict[str, Any],
    db: MongoDep,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Đăng hoặc sửa review cho 1 game"""
    game_id = review_data.get("game_id")
    score = review_data.get("score")
    comment = review_data.get("comment")

    if not game_id or not score:
        raise HTTPException(status_code=400, detail="Missing game_id or score")

    review = UserReview(
        user_id=ObjectId(user_id),
        game_id=ObjectId(game_id),
        score=score,
        comment=comment
    )

    await db.user_reviews.update_one(
        {"user_id": ObjectId(user_id), "game_id": ObjectId(game_id)},
        {"$set": review.to_mongo()},
        upsert=True
    )

    # Trao badge 'reviewer' cho bài đánh giá đầu tiên
    await award_badge(db, user_id, "reviewer")

    return {"status": "success"}


@router.get("/games/{game_id}/reviews/score")
async def get_game_score(game_id: str, db: MongoDep) -> dict[str, Any]:
    """Lấy điểm số trung bình của game (ẩn nếu < 20 lượt)"""
    score = await calculate_game_score(db, game_id)
    # Game chưa đủ lượt đánh giá thì service trả None — `SCHEMA`/PHASE-8 quy
    # định ẩn điểm dưới 20 lượt. Trả về object nói rõ trạng thái, đừng để
    # client tự đoán từ một cái null.
    if score is None:
        return {"score": None, "hidden": True, "reason": "chưa đủ 20 lượt đánh giá"}
    return score


@router.get("/users/{user_id}/badges")
async def get_user_badges(user_id: str, db: MongoDep) -> list[dict[str, Any]]:
    """Xem danh hiệu của 1 user"""
    cursor = db.user_badges.find({"user_id": ObjectId(user_id)})
    badges = await cursor.to_list(length=100)
    return badges
