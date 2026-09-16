"""Feed tin công khai — đường ra duy nhất của kho `articles`.

Trước file này, đường ống tin của Phase 6 **không có chỗ ra nào**: job crawl, khử
trùng, gắn entity và dịch chạy đủ, nhưng `articles` chỉ được job, `services/` và
router `admin` đụng tới. 600 bài đã có tiếng Việt nằm trong Mongo mà không API
hay trang nào đọc được, nên checkpoint "tin quốc tế lên feed tiếng Việt trong
vòng 2 giờ" của `PLAN.md` không thể nghiệm thu.

**Mốc để một bài được lên feed là `summary_vi` đã điền**, không phải
`status == "published"`. Lý do: `status` mặc định là `pending` và KHÔNG có bước
nào trong pipeline nâng nó lên — chỉ `admin.approve_article` làm tay. Lọc theo
`published` thì feed rỗng tuyệt đối (0/1.064 bài). Còn `summary_vi` là mốc nằm
trong chính dữ liệu và nói đúng thứ cần nói: ta đã có bản tiếng Việt TỰ VIẾT để
hiển thị.

Nó cũng khép luôn ràng buộc bản quyền của `CLAUDE.md` ("không tái bản nguyên văn,
chỉ tiêu đề + link + tóm tắt tự viết"): bài không có tóm tắt riêng thì không lên
feed, nên không bao giờ có chuyện hiển thị chay nội dung nguồn.
"""

from __future__ import annotations

from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

Db = AsyncIOMotorDatabase[dict[str, Any]]

ARTICLES = "articles"

# Projection dạng DANH SÁCH CHO PHÉP, không phải danh sách loại trừ.
#
# `original_content` giữ nguyên văn HTML của bài gốc. `CLAUDE.md` cấm tái bản nó,
# nên nó tuyệt đối không được ra khỏi tầng này. Viết kiểu loại trừ
# (`{"original_content": 0}`) thì hôm nay đúng, nhưng ngày mai ai thêm một trường
# thô khác vào model là nó lặng lẽ chảy thẳng ra API công khai.
#
# Cho phép thì phải khai tên; quên khai chỉ làm thiếu dữ liệu — hỏng theo chiều
# an toàn.
FIELDS = {
    "_id": 1,
    "title": 1,
    "translated_title": 1,
    "summary_vi": 1,
    "url": 1,
    "published_at": 1,
    "source_id": 1,
    "game_id": 1,
}


def _chi_lay_bai_co_tieng_viet() -> dict[str, Any]:
    """Điều kiện lọc dùng chung cho cả truy vấn và phép đếm.

    Một hằng số, không phải hai chỗ chép tay: lệch nhau thì `total` nói một đằng
    còn danh sách trả một nẻo, và phân trang sai theo cách rất khó thấy.
    """
    return {
        "summary_vi": {"$nin": [None, ""]},
        # Thừa so với điều kiện trên (job không dịch bài trùng), nhưng nêu tường
        # minh vì nó là ràng buộc về SẢN PHẨM chứ không phải hệ quả tình cờ của
        # thứ tự các job. Nếu sau này có bài trùng lọt vào kèm tóm tắt, dòng này
        # vẫn chặn.
        "status": {"$ne": "duplicate"},
    }


async def _gan_nguon(db: Db, rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Bảng `source_id` -> thông tin nguồn, MỘT truy vấn cho cả lô.

    `articles.source_id` lưu dạng CHUỖI còn `sources._id` là `ObjectId`, nên
    phải đổi kiểu khi join. Join thẳng hai thứ đó trả về rỗng mà không báo lỗi
    gì — chính cái bẫy đã làm một phép đếm trong phiên này ra 0 một cách vô
    nghĩa.
    """
    ids = {str(row["source_id"]) for row in rows if row.get("source_id")}
    if not ids:
        return {}

    object_ids = [ObjectId(i) for i in ids if ObjectId.is_valid(i)]
    out: dict[str, dict[str, Any]] = {}
    cursor = db.sources.find({"_id": {"$in": object_ids}}, {"name": 1, "language": 1})
    async for doc in cursor:
        out[str(doc["_id"])] = {"name": doc.get("name"), "language": doc.get("language")}
    return out


async def _gan_game(db: Db, rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Bảng `game_id` -> tên, slug, ảnh bìa. Cùng lý do đổi kiểu như trên.

    Chỉ 86/600 bài gắn được game, nên phần lớn thẻ tin sẽ không có ảnh — đó là
    trạng thái thật của tầng gắn entity, không phải lỗi hiển thị.
    """
    ids = {str(row["game_id"]) for row in rows if row.get("game_id")}
    if not ids:
        return {}

    object_ids = [ObjectId(i) for i in ids if ObjectId.is_valid(i)]
    out: dict[str, dict[str, Any]] = {}
    cursor = db.games.find(
        {"_id": {"$in": object_ids}}, {"titles": 1, "slug": 1, "media.cover": 1}
    )
    async for doc in cursor:
        titles = doc.get("titles") or {}
        out[str(doc["_id"])] = {
            # Tên tiếng Việt trước, như `/deals`: feed này để người Việt đọc.
            "title": titles.get("vi") or titles.get("primary"),
            "slug": doc.get("slug"),
            "cover_image_url": (doc.get("media") or {}).get("cover"),
        }
    return out


async def public_feed(
    db: Db, *, limit: int = 20, offset: int = 0, game_id: str | None = None
) -> tuple[list[dict[str, Any]], int]:
    """Tin mới nhất trước, kèm tổng số để phân trang.

    `published_at` lưu dạng chuỗi ISO-8601 với hai độ dài khác nhau (có và không
    có phần micro giây), nhưng cả hai đều kết thúc bằng `+00:00`, nên sắp xếp
    theo chuỗi vẫn đúng thứ tự thời gian. Khác biệt duy nhất nằm trong PHẠM VI
    một giây — không đáng để đổi kiểu cả collection.
    """
    limit = max(1, min(limit, 50))
    offset = max(0, offset)

    query = _chi_lay_bai_co_tieng_viet()
    if game_id is not None:
        query["game_id"] = game_id

    collection = db[ARTICLES]
    cursor = (
        collection.find(query, FIELDS).sort("published_at", -1).skip(offset).limit(limit)
    )
    rows = [doc async for doc in cursor]
    total = await collection.count_documents(query)

    nguon = await _gan_nguon(db, rows)
    game = await _gan_game(db, rows)

    articles = [
        {
            "id": str(row["_id"]),
            # Tiêu đề đã dịch nếu có; bản gốc là đường lui, vì một bài có tóm tắt
            # tiếng Việt mà thiếu tiêu đề dịch vẫn đọc được.
            "title": row.get("translated_title") or row.get("title"),
            "summary": row.get("summary_vi"),
            # Link ra nguồn gốc. Đây là thứ thay cho việc tái bản nội dung: muốn
            # đọc đủ thì bấm sang trang của họ.
            "url": row.get("url"),
            "published_at": row.get("published_at"),
            "source": nguon.get(str(row.get("source_id") or "")),
            "game": game.get(str(row.get("game_id") or "")),
        }
        for row in rows
    ]
    return articles, total
