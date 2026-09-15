import asyncio
import datetime as dt
import logging

import feedparser
import httpx

from app.adapters.base import USER_AGENT
from app.models.article import NewsArticle
from app.models.source import Source
from app.services.dedup import compute_simhash

logger = logging.getLogger(__name__)

# Trần chờ MỘT nguồn. Xem giải thích trong `crawl_rss`: không có nó thì một
# nguồn treo là nuốt trọn ngân sách 300 giây của cả job.
FEED_TIMEOUT_SECONDS = 20.0


async def _tai_feed(source: Source, http: httpx.AsyncClient | None) -> bytes | None:
    """Tải thân feed, `None` nếu không lấy được.

    `http` để `None` thì tự dựng client dùng một lần — giữ cho `crawl_rss` gọi
    được từ script rời và từ test mà không phải dựng sẵn client. Job thật thì
    truyền client dùng chung vào, để khỏi bắt tay TLS lại từ đầu với mỗi nguồn.

    **User-Agent là bắt buộc, không phải phép lịch sự.** Khi `feedparser` còn tự
    tải, nó gửi UA riêng của nó và mọi nguồn đều nhận. Chuyển sang httpx là UA
    thành `python-httpx/...`, và **PCGamesN chặn thẳng: 403**. Đo 2026-09-15,
    cùng một URL chỉ đổi mỗi UA thì 403 thành 200.
    """
    headers = {"User-Agent": USER_AGENT}
    try:
        if http is not None:
            resp = await http.get(
                source.url,
                headers=headers,
                timeout=FEED_TIMEOUT_SECONDS,
                follow_redirects=True,
            )
        else:
            async with httpx.AsyncClient(
                timeout=FEED_TIMEOUT_SECONDS, follow_redirects=True, headers=headers
            ) as client:
                resp = await client.get(source.url)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        # Một nguồn chết không được phép làm hỏng lượt của các nguồn còn lại.
        logger.error(f"Không tải được feed từ {source.name}: {exc!r}")
        return None
    return resp.content


async def crawl_rss(source: Source, http: httpx.AsyncClient | None = None) -> list[NewsArticle]:
    """Kéo dữ liệu RSS từ một nguồn và trả về danh sách các bài báo thô."""
    logger.info(f"Đang kéo dữ liệu từ {source.url}...")

    # `feedparser.parse(url)` **tải cả feed qua mạng** một cách đồng bộ, không
    # phải chỉ parse một chuỗi có sẵn. Gọi thẳng trong hàm async thì nó khoá
    # event loop suốt thời gian chờ mạng — với 15 nguồn RSS, worker đứng im
    # từng lượt một và mọi job khác trên cùng tiến trình cũng đứng theo.
    #
    # Đẩy sang thread gỡ được chuyện khoá event loop nhưng KHÔNG gỡ được chuyện
    # chờ vô hạn: `feedparser` tải bằng `urllib` và không nhận tham số timeout
    # nào. Đo 2026-09-15: `cron:crawl_all_sources` chết `TimeoutError` ở đúng
    # 299,99 giây, traceback dừng ngay tại dòng `to_thread` này.
    #
    # Hậu quả nặng hơn một lượt hỏng: job duyệt nguồn theo thứ tự "lâu chưa
    # crawl nhất đi trước" cho công bằng, nên một nguồn treo sẽ bỏ đói **mọi
    # nguồn xếp sau nó**, lượt nào cũng thế — đúng cái mà thứ tự kia sinh ra để
    # tránh.
    #
    # Nên tách hẳn: tải bằng httpx (có timeout thật), rồi mới đưa BYTES cho
    # feedparser. `feedparser.parse` trên bytes không đụng tới mạng.
    raw = await _tai_feed(source, http)
    if raw is None:
        return []

    feed = await asyncio.to_thread(feedparser.parse, raw)

    articles = []
    now = dt.datetime.now(dt.UTC).isoformat()

    # `bozo` KHÔNG phải cờ "hỏng", nó là cờ "có gì đó không chuẩn". Phần lớn
    # trường hợp là cảnh báo hồi phục được — điển hình là
    # `CharacterEncodingOverride` khi feed khai một encoding rồi gửi encoding
    # khác — và feedparser vẫn bóc đủ entry.
    #
    # Coi mọi `bozo` là chí mạng thì một cảnh báo về dấu ngoặc kép là đủ để vứt
    # cả feed. GameK dính đúng thế: `bozo` vì *"declared as us-ascii, but parsed
    # as utf-8"*, và nguồn tiếng Việt ấy câm suốt nhiều ngày dù 50 entry vẫn
    # bóc ra được bình thường.
    #
    # Câu hỏi đúng không phải "có cảnh báo không" mà là **"có bóc được gì
    # không"**. Không entry nào mới là hỏng thật — và đó cũng là hình dạng của
    # một trang HTML báo lỗi trả về thay cho feed.
    if not feed.entries:
        if feed.bozo:
            logger.error(f"Lỗi cú pháp RSS từ {source.name}: {feed.bozo_exception}")
        else:
            logger.warning(f"Feed rỗng từ {source.name}")
        return []

    if feed.bozo:
        logger.warning(
            f"Feed {source.name} không chuẩn nhưng vẫn đọc được "
            f"({len(feed.entries)} entry): {feed.bozo_exception}"
        )

    for entry in feed.entries:
        # Nay đã nhận cả feed không chuẩn, nên không tin entry có đủ trường nữa:
        # thiếu `link` hay `title` thì `NewsArticle` bên dưới ném AttributeError
        # và làm hỏng lượt của CẢ nguồn vì một entry lỗi.
        if not getattr(entry, "link", None) or not getattr(entry, "title", None):
            logger.warning(f"Bỏ entry thiếu link hoặc title từ {source.name}")
            continue

        # Lấy nội dung: tuỳ cấu trúc RSS, có feed để nội dung ở 'content', có feed để ở 'summary'
        content = ""
        if hasattr(entry, 'content'):
            content = entry.content[0].value
        elif hasattr(entry, 'summary'):
            content = entry.summary

        if not content:
            continue

        simhash_val = compute_simhash(content)

        # Bóc tách ngày tháng
        published_at = now
        if hasattr(entry, 'published_parsed') and entry.published_parsed:
            parsed = entry.published_parsed
            published_at = (
                # Tách rời việc gắn tzinfo: truyền tzinfo cùng *args thì kiểm
                # tra kiểu không biết được slice có đúng 6 phần tử hay không.
                dt.datetime(*parsed[:6])
                .replace(tzinfo=dt.UTC)
                .isoformat()
            )

        article = NewsArticle(
            source_id=source.name, # Tạm dùng tên nguồn làm ID
            url=entry.link,
            title=entry.title,
            original_content=content,
            simhash=simhash_val,
            published_at=published_at,
            created_at=now
        )
        articles.append(article)

    logger.info(f"Kéo thành công {len(articles)} bài từ {source.name}")
    return articles
