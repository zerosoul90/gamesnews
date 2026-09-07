"""Entity game chuẩn hoá — xem `docs/SCHEMA.md` mục 1.

Đây là model quan trọng nhất của dự án: mọi collection khác đều trỏ về `games`.
`PHASE-1.md` nói thẳng là sai ở đây thì mọi phase sau đều hỏng và rất khó sửa,
nên model này bám sát `SCHEMA.md` từng field, không tự thêm bớt.

Model chỉ chứa **nội dung** của một game. Hai field siêu dữ liệu — `updated_at`
và `content_hash` — do tầng lưu trữ gắn vào lúc ghi (`services/catalog.py`).
Tách như vậy để `content_hash` băm đúng phần nội dung: nếu `updated_at` nằm
trong model thì mỗi lần chạy job hash lại khác nhau và cơ chế phát hiện thay
đổi thành vô dụng.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from typing import Annotated, Any, Literal

from bson import ObjectId
from pydantic import BaseModel, Field, PlainSerializer, PlainValidator, WithJsonSchema

# --- ObjectId dùng được trong pydantic v2 ----------------------------------
#
# `parent_game` trỏ tới _id của game cha (SCHEMA.md). Pydantic không biết kiểu
# ObjectId của bson nên phải dạy nó: nhận cả ObjectId lẫn chuỗi 24 ký tự, khi
# xuất JSON thì thành chuỗi.


def _validate_object_id(value: Any) -> ObjectId:
    if isinstance(value, ObjectId):
        return value
    if isinstance(value, str) and ObjectId.is_valid(value):
        return ObjectId(value)
    raise ValueError(f"không phải ObjectId hợp lệ: {value!r}")


PyObjectId = Annotated[
    ObjectId,
    PlainValidator(_validate_object_id),
    PlainSerializer(str, return_type=str),
    WithJsonSchema({"type": "string"}),
]


# `type` phân biệt game với DLC/demo/bundle. PHASE-1.md mục 2 xếp đây vào ba
# chỗ dễ làm sai, và mục 6 yêu cầu game chính phải xếp trên DLC khi tìm kiếm.
GameType = Literal["game", "dlc", "demo", "bundle"]


class Titles(BaseModel):
    """Tên hiển thị. `primary` luôn có; `vi`/`ja` chỉ khi thật sự khác.

    Ba khoá này khớp đúng `searchable attributes` mà PHASE-1.md mục 6 liệt kê.
    """

    primary: str
    vi: str | None = None
    ja: str | None = None


class ExternalIds(BaseModel):
    """Bảng ID mapping (PHASE-1.md mục 4).

    `steam_appid` là khoá cầu nối chính — gần như nguồn nào cũng có nó, và
    Phase 2 phụ thuộc hoàn toàn vào độ phủ của field này.
    """

    igdb: int | None = None
    steam_appid: int | None = None
    epic_slug: str | None = None
    epic_namespace: str | None = None
    gog_id: str | None = None
    cheapshark_id: str | None = None
    google_play: str | None = None
    app_store: str | None = None


class ReleaseDate(BaseModel):
    """Một mốc phát hành. Là **mảng** theo region + platform, không phải một
    trường duy nhất — một game ra PC ở Nhật trước, ra console ở phương Tây sau.

    `date` để dạng chuỗi ISO đúng như SCHEMA.md, vì MongoDB không có kiểu ngày
    thuần (chỉ có datetime) và ở đây phần giờ là thông tin giả.
    """

    region: str = "ww"
    date: str | None = None
    platform: str | None = None

    @property
    def year(self) -> int | None:
        if not self.date:
            return None
        try:
            return dt.date.fromisoformat(self.date).year
        except ValueError:
            # Nguồn ngoài hay trả ngày chỉ có năm ("2022") hoặc năm-tháng.
            return int(self.date[:4]) if self.date[:4].isdigit() else None


class Media(BaseModel):
    cover: str | None = None
    screenshots: list[str] = Field(default_factory=list)
    videos: list[str] = Field(default_factory=list)


class SystemRequirements(BaseModel):
    minimum: dict[str, str] = Field(default_factory=dict)
    recommended: dict[str, str] = Field(default_factory=dict)


class Game(BaseModel):
    """Một game = một document trong collection `games`."""

    slug: str
    titles: Titles

    # `aliases` giữ nguyên chữ gốc để hiển thị và duyệt tay.
    # `aliases_normalized` là bản dùng để so khớp — xem services/normalize.py.
    aliases: list[str] = Field(default_factory=list)
    aliases_normalized: list[str] = Field(default_factory=list)

    external_ids: ExternalIds = Field(default_factory=ExternalIds)

    type: GameType = "game"
    parent_game: PyObjectId | None = None  # bắt buộc có với DLC
    series: str | None = None

    platforms: list[str] = Field(default_factory=list)
    genres: list[str] = Field(default_factory=list)
    developers: list[str] = Field(default_factory=list)
    publishers: list[str] = Field(default_factory=list)

    release_dates: list[ReleaseDate] = Field(default_factory=list)

    # Gacha/MMO không có "một ngày ra mắt" — chúng chạy theo mùa.
    is_live_service: bool = False
    current_season: str | None = None

    media: Media = Field(default_factory=Media)
    system_requirements: SystemRequirements = Field(default_factory=SystemRequirements)

    region_locked_vn: bool = False

    @property
    def release_year(self) -> int | None:
        """Năm phát hành sớm nhất, dùng cho facet lọc theo năm.

        Lấy sớm nhất chứ không lấy theo region 'ww': nhiều game Nhật ra ở Nhật
        trước cả năm, và người dùng hỏi "game 2015" là hỏi lần đầu nó xuất hiện.
        """
        years = [year for rd in self.release_dates if (year := rd.year) is not None]
        return min(years) if years else None

    def content_hash(self) -> str:
        """Băm phần nội dung, để job đồng bộ biết cái gì thật sự đổi.

        Không có nó thì mỗi lần chạy lại job sẽ ghi đè cả trăm nghìn document
        và `updated_at` nhảy hết, dù dữ liệu y nguyên — vừa tốn ghi, vừa làm
        job đồng bộ delta của mục 6 mất căn cứ.
        """
        payload = json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def to_mongo(self) -> dict[str, Any]:
        """Document sẵn sàng ghi xuống Mongo.

        Dump ở chế độ json để `ReleaseDate.date` ra chuỗi, rồi trả `parent_game`
        về ObjectId — nó là tham chiếu thật tới _id, để dạng chuỗi thì không
        join ngược được.
        """
        doc = self.model_dump(mode="json")
        doc["parent_game"] = self.parent_game
        return doc
