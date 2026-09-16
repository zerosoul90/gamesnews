from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, model_validator

from app.models.game import PyObjectId

StoreType = Literal["steam", "epic", "gog", "cheapshark", "app_store", "google_play"]


class PriceCurrent(BaseModel):
    """Giá hiện tại của một game tại một store. Update (upsert) liên tục."""

    game_id: PyObjectId
    store: StoreType
    region: str = "vn"
    currency: str = "VND"

    price_initial: int
    price_final: int
    discount_percent: int

    is_free_promo: bool = False
    promo_ends_at: str | None = None

    lowest_ever: int | None = None
    lowest_ever_date: str | None = None
    is_historical_low: bool = False
    # Số lần đã quan sát được giá của game này. `services/pricing.py` cần nó để
    # biết mình có đủ lịch sử để nói "đang ở đáy" hay chưa — ở lượt quét đầu
    # tiên thì `lowest_ever` chỉ là giá vừa đọc, không phải một cái đáy.
    observations: int = 0

    url: str | None = None
    checked_at: str | None = None

    @model_validator(mode="after")
    def _chan_giam_gia_mau_thuan(self) -> PriceCurrent:
        """Giá gốc bằng giá bán thì mức giảm phải là 0.

        Đo trên dữ liệu thật 2026-09-16: Crystal Crisis nằm ở
        `discount_percent: 100` trong khi `price_initial == price_final == 188000`
        và `is_free_promo: false`. Trang deal sắp theo `discount_percent` giảm
        dần nên bản ghi ấy **nhảy lên vị trí đầu tiên**, hiện "-100%" ngay cạnh
        giá 188.000₫ — con số vô lý nhất trang lại là thứ đầu tiên người ta thấy.

        Chỉ một bản ghi trong cả kho bị vậy, nên đây không phải lỗi hệ thống mà
        là dữ liệu bên ngoài tự mâu thuẫn: nhiều khả năng Steam trả
        `discount_percent` còn sót lại của một đợt giảm vừa kết thúc trong khi
        hai trường giá đã cập nhật.

        **Tin hai trường giá, không tin trường mức giảm.** Giá là thứ người dùng
        trả và là thứ ta đối chiếu được; `discount_percent` chỉ là số dẫn xuất mà
        nguồn tự tính. Nên khi hai bên đá nhau thì tính lại từ giá.

        Không ném lỗi: hai trường giá vẫn đúng và vẫn đáng lưu. Vứt cả bản ghi vì
        một trường dẫn xuất sai là mất một mức giá thật — cùng lý lẽ với nhánh
        "model trả rác thì vẫn lưu bài" của job tin.

        Ca `is_free_promo` KHÔNG bị đụng tới: ở đó `price_final = 0` khác
        `price_initial`, nên `discount_percent = 100` là nhất quán.
        """
        if self.price_initial > 0 and self.price_final == self.price_initial:
            self.discount_percent = 0
        return self

    def to_mongo(self) -> dict[str, Any]:
        doc = self.model_dump(mode="json", exclude_none=True)
        doc["game_id"] = self.game_id
        return doc


class PriceHistory(BaseModel):
    """Lịch sử giá, chỉ append khi có thay đổi."""

    game_id: PyObjectId
    store: StoreType
    region: str = "vn"
    price_final: int
    discount_percent: int
    changed_at: str

    def to_mongo(self) -> dict[str, Any]:
        doc = self.model_dump(mode="json")
        doc["game_id"] = self.game_id
        return doc
