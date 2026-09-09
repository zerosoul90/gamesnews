import datetime as dt
import logging

import feedparser

from app.models.article import NewsArticle
from app.models.source import Source
from app.services.dedup import compute_simhash

logger = logging.getLogger(__name__)

async def crawl_rss(source: Source) -> list[NewsArticle]:
    """Kéo dữ liệu RSS từ một nguồn và trả về danh sách các bài báo thô."""
    logger.info(f"Đang kéo dữ liệu từ {source.url}...")

    # feedparser.parse() là hàm đồng bộ, nhưng chạy khá nhanh.
    # Nếu tải nặng cần đẩy vào threadpool, tạm thời cứ gọi trực tiếp.
    feed = feedparser.parse(source.url)

    articles = []
    now = dt.datetime.now(dt.UTC).isoformat()

    if feed.bozo:
        logger.error(f"Lỗi cú pháp RSS từ {source.name}: {feed.bozo_exception}")
        return []

    for entry in feed.entries:
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
