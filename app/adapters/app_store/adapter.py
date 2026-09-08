"""App Store — `docs/PHASE-1.md` mục 5.

`DATA-SOURCES.md` ghi "thư viện scraper open source" cho hai store mobile. Với
App Store thì không cần: Apple có sẵn hai endpoint JSON công khai, miễn phí,
không key và có tài liệu — ổn định hơn hẳn một thư viện bóc HTML, mà thực chất
các thư viện đó cũng chỉ bọc lại đúng hai endpoint này.

- Bảng xếp hạng: `rss.marketingtools.apple.com/api/v2/{country}/apps/{feed}/...`
- Chi tiết: `itunes.apple.com/lookup?id=...` — **gộp được 200 id một lần gọi**,
  nên lấy chi tiết cả bảng xếp hạng chỉ tốn vài request.

Hai endpoint trả về hai hình dạng khác nhau cho cùng một app (`id`/`name` so
với `trackId`/`trackName`), nên `to_game` đọc được cả hai — bảng xếp hạng đã đủ
dựng entity, `lookup` chỉ bồi thêm ảnh chụp màn hình và thể loại chi tiết.

Hạn mức Apple công bố cho iTunes API là ~20 request/phút. Bucket đặt đúng con
số đó và nằm trong Redis nên nhiều worker dùng chung một hạn mức.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar, Literal

import httpx

from app.adapters.base import (
    AdapterConfig,
    BaseAdapter,
    PermanentError,
    RateLimit,
    TransientError,
    classify_http_status,
)
from app.models.game import ExternalIds, Game, Media, ReleaseDate, Titles
from app.services.normalize import slugify

logger = logging.getLogger(__name__)

RSS_BASE = "https://rss.marketingtools.apple.com/api/v2"
LOOKUP_URL = "https://itunes.apple.com/lookup"

# Apple công bố ~20 request/phút cho iTunes API.
RATE_LIMIT = RateLimit(capacity=20, per_seconds=60.0)

# Một lần lookup nhận tối đa 200 id.
LOOKUP_BATCH = 200

# Mã thể loại "Games". Bảng xếp hạng trả về đủ mọi loại app nên phải lọc, và
# đây là cách lọc rẻ nhất: ngay trên payload bảng xếp hạng, trước khi lookup.
GAMES_GENRE_ID = "6014"

Feed = Literal["top-free", "top-paid", "top-grossing"]

# `genres` của iTunes luôn mở đầu bằng nhãn ô dù "Games" rồi mới tới thể loại
# con. Giữ nhãn đó thì mọi game mobile đều có chung một thể loại vô nghĩa.
_UMBRELLA_GENRES = frozenset({"games", "entertainment"})


def _is_game(entry: dict[str, Any]) -> bool:
    """Chỉ đúng với payload bảng xếp hạng, nơi `genres` là danh sách object."""
    return any(str(g.get("genreId")) == GAMES_GENRE_ID for g in entry.get("genres", []))


def _genre_names(result: dict[str, Any]) -> list[str]:
    """`genres` là list chuỗi ở `lookup`, list object ở bảng xếp hạng."""
    out: list[str] = []
    for item in result.get("genres", []):
        name = item.get("name") if isinstance(item, dict) else item
        if name:
            out.append(str(name))
    return out


def to_game(result: dict[str, Any], *, international_name: str | None = None) -> Game:
    """Một record của Apple -> entity `games`. Nhận cả hai hình dạng payload.

    `international_name` là tên ở gian hàng Mỹ. Có nó thì tên quốc tế làm
    `titles.primary` còn tên gian hàng VN thành `titles.vi` — đúng hình dạng
    `SCHEMA.md` mô tả, và là thứ giúp ghép được với bản Google Play.
    """
    store_id = result.get("trackId") or result.get("id")
    if store_id is None:
        raise PermanentError(f"record App Store thiếu id: {result.get('trackName')!r}")

    vn_name = str(result.get("trackName") or result.get("name") or "").strip()
    if not vn_name:
        raise PermanentError(f"record App Store thiếu tên: {store_id}")

    primary = (international_name or vn_name).strip()
    released = str(result.get("releaseDate") or "")
    genres = [
        slug
        for name in _genre_names(result)
        if (slug := slugify(name)) not in _UMBRELLA_GENRES
    ]

    return Game(
        slug=slugify(primary),
        titles=Titles(primary=primary, vi=vn_name if vn_name != primary else None),
        # App Store chỉ lộ tên tài khoản bán, tức nhà phát hành. Ai thật sự làm
        # ra game thì store không nói, nên `developers` để trống chứ không chép
        # sang cho đầy.
        publishers=[str(result["artistName"])] if result.get("artistName") else [],
        external_ids=ExternalIds(app_store=str(store_id)),
        platforms=["ios"],
        genres=genres,
        release_dates=(
            [ReleaseDate(region="vn", date=released[:10], platform="ios")] if released else []
        ),
        media=Media(
            cover=result.get("artworkUrl512") or result.get("artworkUrl100"),
            screenshots=[str(url) for url in result.get("screenshotUrls", [])],
        ),
    )


def with_international_name(game: Game, name: str | None) -> Game:
    """Gắn tên gian hàng Mỹ làm tên chính, đẩy tên gian hàng VN xuống `titles.vi`.

    Slug đi theo tên chính, vì slug sinh từ tên tiếng Việt thì URL ra một chuỗi
    không ai gõ được và không khớp với nguồn nào khác.
    """
    vn_name = game.titles.primary
    if not name or name == vn_name:
        return game
    return game.model_copy(
        update={
            "slug": slugify(name),
            "titles": Titles(primary=name, vi=vn_name, ja=game.titles.ja),
        }
    )


class AppStoreAdapter(BaseAdapter[list[dict[str, Any]], list[Game]]):
    """Hai thao tác: lấy bảng xếp hạng, và tra chi tiết theo lô id."""

    source: ClassVar[str] = "app_store"

    def __init__(
        self,
        config: AdapterConfig,
        http: httpx.AsyncClient,
        *,
        country: str = "vn",
    ) -> None:
        super().__init__(config)
        self._http = http
        self._country = country

    async def _get_json(self, url: str, params: dict[str, str] | None = None) -> Any:
        try:
            response = await self._http.get(url, params=params)
        except httpx.HTTPError as exc:
            # Đứt mạng hay timeout là lỗi tạm thời — để lớp cơ sở retry.
            raise TransientError(f"không gọi được {url}: {exc!r}") from exc

        error = classify_http_status(response.status_code)
        if error is not None:
            raise error(f"{url} -> {response.status_code}: {response.text[:200]}")
        try:
            return response.json()
        except ValueError as exc:
            raise PermanentError(f"{url} trả về không phải JSON: {exc}") from exc

    async def fetch_raw(self, **params: Any) -> list[dict[str, Any]]:
        operation = params["op"]

        if operation == "chart":
            payload = await self._get_json(
                f"{RSS_BASE}/{self._country}/apps/{params['feed']}/{params['limit']}/apps.json"
            )
            results = (payload or {}).get("feed", {}).get("results", [])
            return [entry for entry in results if _is_game(entry)]

        if operation == "lookup":
            payload = await self._get_json(
                LOOKUP_URL,
                {
                    "id": ",".join(params["ids"]),
                    "country": params["country"],
                    "entity": "software",
                },
            )
            return list((payload or {}).get("results", []))

        raise PermanentError(f"thao tác không biết: {operation!r}")

    def normalize(self, raw: list[dict[str, Any]]) -> list[Game]:
        games: list[Game] = []
        for result in raw:
            try:
                games.append(to_game(result))
            except PermanentError as exc:
                # Một record hỏng không được làm hỏng cả lô 200.
                logger.warning("bỏ qua record App Store", extra={"error": str(exc)})
        return games

    async def chart(self, feed: Feed, *, limit: int = 200) -> list[Game]:
        """Game trong một bảng xếp hạng của gian hàng VN.

        Bảng xếp hạng đã đủ dựng entity; `details` chỉ bồi thêm.
        """
        return await self.fetch(endpoint=f"chart/{feed}", op="chart", feed=feed, limit=limit)

    async def details(self, ids: list[str], *, country: str | None = None) -> list[Game]:
        out: list[Game] = []
        for start in range(0, len(ids), LOOKUP_BATCH):
            out += await self.fetch(
                endpoint="lookup",
                op="lookup",
                ids=ids[start : start + LOOKUP_BATCH],
                country=country or self._country,
            )
        return out

    async def international_names(self, ids: list[str]) -> dict[str, str]:
        """Tên ở gian hàng Mỹ, để làm `titles.primary`.

        Không có bước này thì mọi game mobile vào catalog dưới tên tiếng Việt,
        và không còn đường nào ghép nó với bản Google Play hay với IGDB sau này.
        Game không bán ở Mỹ thì đơn giản không có trong kết quả.
        """
        return {
            game.external_ids.app_store: game.titles.primary
            for game in await self.details(ids, country="us")
            if game.external_ids.app_store
        }
