from typing import Any, Literal

from pydantic import BaseModel

ArticleStatus = Literal["pending", "published", "duplicate", "error"]

class NewsArticle(BaseModel):
    source_id: str
    url: str
    title: str
    original_content: str # Dữ liệu thô trước khi tóm tắt
    simhash: str # Giá trị hash khoảng cách

    status: ArticleStatus = "pending"
    duplicate_of: str | None = None # _id của bài gốc nếu bị trùng

    # Entity Matching.
    #
    # `alias`, không phải `fuzzy`: `services/entity_matcher` đã bỏ hẳn cách so
    # chuỗi mờ (nó so CẢ tiêu đề với từng alias nên gần như không bao giờ khớp)
    # và thay bằng khớp CHÍNH XÁC trên cụm từ đã chuẩn hoá. Để tên cũ ở đây thì
    # tầng lưu trữ và tầng nghiệp vụ gọi cùng một thứ bằng hai tên.
    game_id: str | None = None
    matching_tier: Literal["exact", "alias", "embedding", "manual", "none"] = "none"
    confidence_score: float = 0.0 # Ngưỡng tin cậy

    # LLM Output
    translated_title: str | None = None
    summary_vi: str | None = None

    published_at: str | None = None # Thời gian phát hành từ RSS
    created_at: str | None = None

    def to_mongo(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
