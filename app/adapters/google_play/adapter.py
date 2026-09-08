"""Google Play — `docs/PHASE-1.md` mục 5.

Google không có API công khai cho Play Store, nên đúng như `DATA-SOURCES.md`
nói, phần này dựa vào thư viện scraper open source (`google-play-scraper`).
Phần "dễ vỡ" để cộng đồng bảo trì, ta chỉ bọc nó lại sau adapter của mình để
được hưởng token bucket, retry và phân loại lỗi.

Hai điều thư viện đó áp đặt lên thiết kế ở đây:

1. **Nó đồng bộ.** Gọi thẳng trong event loop là chặn cả worker, nên mọi lời
   gọi đi qua `asyncio.to_thread`.
2. **Nó không có hàm lấy bảng xếp hạng** (bản 1.2.7 chỉ có `app`, `search`,
   `reviews`, `permissions`). Nguồn khám phá vì vậy là `search`: tìm theo tên
   game lấy từ bảng xếp hạng App Store, cộng thêm một danh sách từ khoá tiếng
   Việt để bắt game chỉ có trên Android.

Hai hàm của thư viện được tiêm vào qua constructor, không import cứng: test
không được phép gọi ra Internet thật.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
from collections.abc import Callable
from typing import Any, ClassVar

from app.adapters.base import (
    AdapterConfig,
    BaseAdapter,
    PermanentError,
    RateLimit,
    TransientError,
)
from app.models.game import ExternalIds, Game, Media, ReleaseDate, Titles
from app.services.normalize import slugify

logger = logging.getLogger(__name__)

# Google không công bố hạn mức nào; đây là mức tự đặt cho lịch sự. Quá tay thì
# Play chặn theo IP, mà mất IP là mất luôn cả nguồn.
RATE_LIMIT = RateLimit(capacity=1, per_seconds=1.0)

# `genreId` của mọi thể loại game đều mở đầu bằng GAME. Đây là bộ lọc tin cậy
# duy nhất, nhưng CHỈ payload của `app()` mới có trường này — kết quả `search`
# chỉ có `genre` đã bản địa hoá ("Hành động"), không lọc được. Vì vậy phải gọi
# `app()` cho cả app không phải game rồi mới loại được nó.
GAME_GENRE_PREFIX = "GAME"

# `released` của Play là chuỗi đã bản địa hoá theo `lang`, nên chỉ đọc được từ
# payload tiếng Anh. Không parse được thì bỏ, đừng đoán.
_RELEASED_FORMAT = "%b %d, %Y"

AppFetcher = Callable[..., dict[str, Any]]
SearchFetcher = Callable[..., list[dict[str, Any]]]


def _released_iso(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return dt.datetime.strptime(value.strip(), _RELEASED_FORMAT).date().isoformat()
    except ValueError:
        logger.debug("không đọc được ngày phát hành Play", extra={"value": value})
        return None


def is_game(payload: dict[str, Any]) -> bool:
    return str(payload.get("genreId") or "").startswith(GAME_GENRE_PREFIX)


def to_game(payload: dict[str, Any], *, vietnamese_name: str | None = None) -> Game:
    """Payload `app()` của Play -> entity `games`.

    Gọi với `lang="en"` để có tên quốc tế làm `titles.primary`; tên tiếng Việt
    lấy riêng ở lần gọi `lang="vi"` rồi truyền vào đây. Ngược lại thì mọi game
    vào catalog dưới đúng một thứ tiếng và mất đường ghép với nguồn khác.
    """
    app_id = payload.get("appId")
    if not app_id:
        raise PermanentError("payload Play thiếu appId")

    primary = str(payload.get("title") or "").strip()
    if not primary:
        raise PermanentError(f"payload Play thiếu title: {app_id}")

    vi = (vietnamese_name or "").strip() or None
    released = _released_iso(payload.get("released"))

    return Game(
        slug=slugify(primary),
        titles=Titles(primary=primary, vi=vi if vi and vi != primary else None),
        # Play chỉ lộ tên tài khoản nhà phát triển, thực chất là nhà phát hành.
        publishers=[str(payload["developer"])] if payload.get("developer") else [],
        external_ids=ExternalIds(google_play=str(app_id)),
        platforms=["android"],
        genres=[slugify(str(payload["genre"]))] if payload.get("genre") else [],
        release_dates=(
            [ReleaseDate(region="vn", date=released, platform="android")] if released else []
        ),
        media=Media(
            cover=payload.get("icon"),
            screenshots=[str(url) for url in payload.get("screenshots", [])],
        ),
    )


class GooglePlayAdapter(BaseAdapter[list[dict[str, Any]], list[dict[str, Any]]]):
    """Trả về payload thô đã lọc còn game, việc dựng `Game` để `to_game` lo.

    Khác hai adapter khác ở chỗ `normalize` không đổi sang `Game` ngay: một
    entity Play cần **hai** payload (tiếng Anh và tiếng Việt) mới đủ tên, mà
    `fetch` của lớp cơ sở thì mỗi lần chỉ mang về được một payload.
    """

    source: ClassVar[str] = "google_play"

    def __init__(
        self,
        config: AdapterConfig,
        *,
        app_fetcher: AppFetcher | None = None,
        search_fetcher: SearchFetcher | None = None,
        country: str = "vn",
    ) -> None:
        super().__init__(config)
        self._country = country
        self._app = app_fetcher or _default_app_fetcher()
        self._search = search_fetcher or _default_search_fetcher()

    async def fetch_raw(self, **params: Any) -> list[dict[str, Any]]:
        operation = params["op"]
        try:
            if operation == "app":
                # Thư viện đồng bộ: chạy trong thread, không chặn event loop.
                payload = await asyncio.to_thread(
                    self._app,
                    params["app_id"],
                    lang=params["lang"],
                    country=self._country,
                )
                return [payload]

            if operation == "search":
                hits = await asyncio.to_thread(
                    self._search,
                    params["query"],
                    n_hits=params["limit"],
                    lang=params["lang"],
                    country=self._country,
                )
                return list(hits)
        except Exception as exc:  # thư viện ném đủ loại lỗi mạng của riêng nó
            name = type(exc).__name__
            if name in ("NotFoundError", "ExtraHTTPError"):
                raise PermanentError(f"play {operation}: {exc!r}") from exc
            raise TransientError(f"play {operation}: {exc!r}") from exc

        raise PermanentError(f"thao tác không biết: {operation!r}")

    def normalize(self, raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return raw

    async def search_games(self, query: str, *, limit: int = 30) -> list[str]:
        """`appId` của các app khớp từ khoá, ở gian hàng VN.

        **Kết quả đầu bảng thường bị mất.** Play dựng thẻ kết quả đầu tiên khác
        các thẻ còn lại, và thư viện không bóc được `appId` của nó — trả về
        None (kiểm bằng tay ngày 2026-09-08: tìm "Liên Quân Mobile" thì 4/5 kết
        quả có appId, riêng cái đầu thì không). Đây đúng là chỗ
        `DATA-SOURCES.md` cảnh báo "dễ vỡ, cần giám sát", nên số hit rơi được
        ghi log để còn thấy khi nó vỡ thêm.

        Chưa lọc game ở đây: kết quả `search` không có `genreId`. Việc lọc nằm
        ở `detail`.
        """
        hits = await self.fetch(
            endpoint="search", op="search", query=query, limit=limit, lang="vi"
        )
        app_ids = [str(hit["appId"]) for hit in hits if hit.get("appId")]
        if (dropped := len(hits) - len(app_ids)) > 0:
            logger.info(
                "play: bỏ hit không bóc được appId",
                extra={"query": query, "dropped": dropped, "total": len(hits)},
            )
        return app_ids

    async def detail(self, app_id: str) -> Game | None:
        """Entity đầy đủ của một app. Trả None nếu app đó không phải game.

        Tốn hai request: bản tiếng Anh cho tên quốc tế và ngày phát hành (chuỗi
        ngày của Play bản địa hoá theo `lang`), bản tiếng Việt cho `titles.vi`.
        """
        english = (await self.fetch(endpoint="app", op="app", app_id=app_id, lang="en"))[0]
        if not is_game(english):
            return None

        vietnamese = (await self.fetch(endpoint="app", op="app", app_id=app_id, lang="vi"))[0]
        return to_game(english, vietnamese_name=str(vietnamese.get("title") or ""))


def _default_app_fetcher() -> AppFetcher:
    from google_play_scraper import app as play_app

    fetcher: AppFetcher = play_app
    return fetcher


def _default_search_fetcher() -> SearchFetcher:
    from google_play_scraper import search as play_search

    fetcher: SearchFetcher = play_search
    return fetcher
