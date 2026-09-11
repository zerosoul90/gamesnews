"""Sitemap và robots.txt — `docs/PHASE-4.md` mục 5.

Checkpoint "Sitemap hợp lệ, Google Search Console không báo lỗi cấu trúc" đã
được đánh dấu xong từ lâu, nhưng `GET /sitemap.xml` và `GET /robots.txt` đều
trả 404 — Phase 4 mới chỉ có thẻ meta động, không có sitemap nào.

**Vì sao sitemap nằm ở FastAPI chứ không ở Angular.** Nó phải liệt kê hàng chục
nghìn slug, tức là phải đọc Mongo; còn `server.ts` chỉ có proxy `/api`. Express
chuyển tiếp đúng ba đường dẫn của file này về đây (xem `mountSeoProxy`), nên với
người ngoài chúng vẫn nằm cùng origin với trang — điều kiện bắt buộc: Google chỉ
nhận sitemap nằm trên chính host mà nó liệt kê.

**Vì sao phải chia trang.** Chuẩn sitemap cho tối đa 50.000 URL và 50 MB mỗi
file. Catalog đang trên đường tới ~185.000 game, nên `/sitemap.xml` là một
*sitemap index* trỏ sang các file con. Trang nhỏ hơn trần khá nhiều vì mỗi file
được dựng ngay trong request: 10.000 dòng đọc từ Mongo là vừa đủ nhanh.
"""

from __future__ import annotations

import datetime as dt
import math
from typing import Any
from xml.sax.saxutils import escape

from fastapi import APIRouter, HTTPException, Response
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import get_settings
from app.core.deps import MongoDep

router = APIRouter(tags=["SEO"])

Db = AsyncIOMotorDatabase[dict[str, Any]]

# Số URL mỗi file con.
PAGE_SIZE = 10_000

# DLC không vào sitemap. Trang của một DLC gần như không có nội dung riêng — giá
# thì thường không bán lẻ ở VN, mô tả thì trỏ về game cha — và đẩy vài chục
# nghìn trang mỏng cho Google index là cách nhanh nhất để bị đánh giá thấp cả
# tên miền. Người dùng vẫn tới được DLC từ trang game cha.
GAME_FILTER: dict[str, Any] = {"slug": {"$exists": True, "$ne": None}, "type": {"$ne": "dlc"}}

# Trang không sinh từ catalog. Khớp `web/src/app/app.routes.ts`; `/` đã 302 sang
# `/deals` ở `server.ts` nên chỉ liệt kê đích, không liệt kê cả hai.
STATIC_PATHS = [("/deals", "hourly"), ("/free", "daily")]

XML_HEADERS = {"Cache-Control": "public, max-age=3600"}


def _base_url() -> str:
    """Origin công khai, hoặc 503 kèm lời giải thích.

    Sitemap gồm toàn URL tuyệt đối, và đoán origin từ header `Host` không dùng
    được ở đây: Express ghi đè `host` thành `app:8000` khi chuyển tiếp, nên ta
    sẽ sinh ra một sitemap đầy địa chỉ nội bộ và nộp nó cho Google. Thà chết ồn
    ào — cùng lý lẽ với `JWT_SECRET`.
    """
    base = get_settings().public_base_url.rstrip("/")
    if not base:
        raise HTTPException(
            status_code=503,
            detail=(
                "PUBLIC_BASE_URL chưa cấu hình. Sitemap cần URL tuyệt đối, "
                "không suy ra được từ request khi đứng sau proxy."
            ),
        )
    return base


def _xml(body: str) -> Response:
    return Response(content=body, media_type="application/xml", headers=XML_HEADERS)


def _lastmod(value: Any) -> str:
    """`updated_at` -> W3C Datetime, hoặc chuỗi rỗng khi không đọc được.

    Không dùng thẳng `str(value)`: `updated_at` nằm trong Mongo dưới dạng
    `datetime`, và `str(datetime)` ra `2026-09-07 16:28:45.910000+00:00` —
    **dấu cách** thay cho `T`. Chuẩn sitemap đòi W3C Datetime, và một `lastmod`
    sai định dạng bị Google bỏ qua lặng lẽ, không có dòng lỗi nào trong Search
    Console. Đúng loại hỏng mà nhìn từ ngoài thì sitemap vẫn "chạy".
    """
    if isinstance(value, dt.datetime):
        return value.isoformat()
    if isinstance(value, str):
        # Vài collection ghi ISO sẵn dưới dạng chuỗi. Parse rồi phát lại để một
        # chuỗi rác không lọt vào XML dưới danh nghĩa ngày tháng.
        try:
            return dt.datetime.fromisoformat(value).isoformat()
        except ValueError:
            return ""
    return ""


async def _count_games(db: Db) -> int:
    count: int = await db.games.count_documents(GAME_FILTER)
    return count


@router.get("/robots.txt", response_class=Response)
async def robots_txt() -> Response:
    """Cho phép index, và chỉ đường tới sitemap.

    `/admin` bị chặn: nó là trang sửa được cả catalog, không có lý do gì để nằm
    trong kết quả tìm kiếm. Đây không phải một lớp bảo mật — `ADMIN_TOKEN` mới
    là — chỉ là không mời bot vào.
    """
    lines = ["User-agent: *", "Allow: /", "Disallow: /admin", "Disallow: /api/"]

    # Thiếu PUBLIC_BASE_URL thì bỏ dòng Sitemap chứ không trả 503: robots.txt
    # hỏng nghĩa là bot không biết được phép đọc gì, tệ hơn nhiều so với việc
    # nó phải tự tìm sitemap.
    base = get_settings().public_base_url.rstrip("/")
    if base:
        lines.append(f"Sitemap: {base}/sitemap.xml")

    return Response(
        content="\n".join(lines) + "\n",
        media_type="text/plain",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/sitemap.xml", response_class=Response)
async def sitemap_index(db: MongoDep) -> Response:
    """Sitemap index: trang tĩnh + n file con của catalog."""
    base = _base_url()
    total = await _count_games(db)
    # Luôn có ít nhất một file con, kể cả catalog rỗng: một index trỏ đi đâu
    # cũng không có là cấu trúc Search Console báo lỗi.
    pages = max(1, math.ceil(total / PAGE_SIZE))

    entries = [f"<sitemap><loc>{base}/sitemap-pages.xml</loc></sitemap>"]
    entries += [
        f"<sitemap><loc>{base}/sitemap-games-{page}.xml</loc></sitemap>"
        for page in range(1, pages + 1)
    ]

    return _xml(
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + "".join(entries)
        + "</sitemapindex>"
    )


@router.get("/sitemap-pages.xml", response_class=Response)
async def sitemap_pages() -> Response:
    """Các trang không sinh từ catalog."""
    base = _base_url()
    urls = [
        f"<url><loc>{base}{path}</loc><changefreq>{freq}</changefreq>"
        f"<priority>0.9</priority></url>"
        for path, freq in STATIC_PATHS
    ]
    return _xml(
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + "".join(urls)
        + "</urlset>"
    )


@router.get("/sitemap-games-{page}.xml", response_class=Response)
async def sitemap_games(db: MongoDep, page: int) -> Response:
    """Một trang slug game.

    Sắp theo `_id` chứ không theo `updated_at`: thứ tự phải ổn định giữa hai
    lần gọi, nếu không thì game bị đẩy từ trang 2 sang trang 1 trong lúc Google
    đang đọc dở và nó không bao giờ thấy được.
    """
    base = _base_url()
    if page < 1:
        raise HTTPException(status_code=404, detail="Không có trang này")

    cursor = (
        db.games.find(GAME_FILTER, {"slug": 1, "updated_at": 1})
        .sort("_id", 1)
        .skip((page - 1) * PAGE_SIZE)
        .limit(PAGE_SIZE)
    )
    rows = await cursor.to_list(None)
    if not rows and page > 1:
        raise HTTPException(status_code=404, detail="Không có trang này")

    urls = []
    for row in rows:
        loc = f"{base}/game/{escape(str(row['slug']), {'"': '&quot;'})}"
        lastmod = _lastmod(row.get("updated_at"))
        mod = f"<lastmod>{lastmod}</lastmod>" if lastmod else ""
        urls.append(f"<url><loc>{loc}</loc>{mod}<changefreq>weekly</changefreq></url>")

    return _xml(
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + "".join(urls)
        + "</urlset>"
    )
