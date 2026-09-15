from typing import Any, Literal

from pydantic import BaseModel

SourceStatus = Literal["active", "inactive", "error"]

class Source(BaseModel):
    name: str
    url: str # feed URL
    language: str = "en" # "en" or "vi"
    reliability_score: int = 100 # Ngưỡng tin cậy, 0-100
    status: SourceStatus = "active"
    last_crawled_at: str | None = None # ISO format
    # Số lượt LIÊN TIẾP kéo được 0 bài. Một nguồn câm không làm job đỏ và cũng
    # không làm tổng `fetched` về 0 — nó chỉ lặng lẽ biến mất khỏi một con số
    # hàng trăm. Đây là chỗ phân biệt "trục trặc một lượt" với "chết hẳn".
    # Xem `services/sources.ghi_nhan_so_bai`.
    empty_streak: int = 0

    def to_mongo(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
