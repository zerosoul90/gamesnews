"""App Store — `docs/PHASE-1.md` mục 5.

`DATA-SOURCES.md` ghi "thư viện scraper open source" cho hai store mobile. Với
App Store thì không cần: Apple có sẵn các endpoint JSON công khai, miễn phí,
không key — ổn định hơn hẳn một thư viện bóc HTML, mà thực chất các thư viện đó
cũng chỉ bọc lại đúng chúng.

Ba endpoint, và **vai trò của chúng là kết quả của việc thử thật** (kiểm bằng
tay ngày 2026-09-08):

- `itunes.apple.com/search` — **nguồn khám phá chính**. Mỗi từ khoá trả về
  ~150 kết quả, hầu hết là game, và payload đã đủ dựng entity.
- `itunes.apple.com/{country}/rss/{kind}/limit=N/genre=6014/json` — bảng xếp
  hạng game của gian hàng VN. Endpoint đời cũ, nhưng là **cái duy nhất lọc
  được theo thể loại**: API marketing v2 mới hơn chỉ có bảng "apps", mà bảng đó
  loại hẳn game — kiểm 100/100 mục đầu bảng VN đều là Finance/Photo/Business,
  không một game nào — và trong v2 không tồn tại bảng games. Apple có khai tử
  nốt endpoint này thì search vẫn chạy: bảng xếp hạng là phần bồi thêm, không
  phải chỗ dựa.
- `itunes.apple.com/lookup` — chi tiết theo lô, **gộp 200 id một lần gọi**.

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

SEARCH_URL = "https://itunes.apple.com/search"
LOOKUP_URL = "https://itunes.apple.com/lookup"
RSS_URL = "https://itunes.apple.com/{country}/rss/{kind}/limit={limit}/genre={genre}/json"

# Apple công bố ~20 request/phút cho iTunes API.
RATE_LIMIT = RateLimit(capacity=20, per_seconds=60.0)

# Một lần lookup nhận tối đa 200 id; search cũng nhận limit tối đa 200.
LOOKUP_BATCH = 200
SEARCH_LIMIT = 200

# Trần bảng xếp hạng đã kiểm thật: 100 chạy tốt.
CHART_LIMIT = 100

# Mã thể loại "Games" của App Store.
GAMES_GENRE_ID = "6014"

# Tên bảng xếp hạng của endpoint RSS đời cũ, giấu sau tên gọi dễ đọc.
Feed = Literal["top-free", "top-paid", "top-grossing"]
_FEED_KINDS: dict[str, str] = {
    "top-free": "topfreeapplications",
    "top-paid": "toppaidapplications",
    "top-grossing": "topgrossingapplications",
}

# `genres` của iTunes luôn mở đầu bằng nhãn ô dù "Games" rồi mới tới thể loại
# con. Giữ nhãn đó thì mọi game mobile đều có chung một thể loại vô nghĩa.
_UMBRELLA_GENRES = frozenset({"games", "entertainment"})


def is_game(result: dict[str, Any]) -> bool:
    """Chỉ dùng được với payload `search`/`lookup`; RSS đã lọc sẵn theo genre."""
    return str(result.get("primaryGenreId")) == GAMES_GENRE_ID


def to_game(result: dict[str, Any], *, international_name: str | None = None) -> Game:
    """Một record `search`/`lookup` -> entity `games`.

    `international_name` là tên ở gian hàng Mỹ. Có nó thì tên quốc tế làm
    `titles.primary` còn tên gian hàng VN thành `titles.vi` — đúng hình dạng
    `SCHEMA.md` mô tả, và là thứ giúp ghép được với bản Google Play.
    """
    track_id = result.get("trackId")
    if track_id is None:
        raise PermanentError(f"record App Store thiếu trackId: {result.get('trackName')!r}")

    vn_name = str(result.get("trackName") or "").strip()
    if not vn_name:
        raise PermanentError(f"record App Store thiếu trackName: {track_id}")

    primary = (international_name or vn_name).strip()
    released = str(result.get("releaseDate") or "")
    genres = [
        slug
        for name in result.get("genres", [])
        if (slug := slugify(str(name))) not in _UMBRELLA_GENRES
    ]

    return Game(
        slug=slugify(primary),
        titles=Titles(primary=primary, vi=vn_name if vn_name != primary else None),
        # App Store chỉ lộ tên tài khoản bán, tức nhà phát hành. Ai thật sự làm
        # ra game thì store không nói, nên `developers` để trống chứ không chép
        # sang cho đầy.
        publishers=[str(result["artistName"])] if result.get("artistName") else [],
        external_ids=ExternalIds(app_store=str(track_id)),
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

    Slug đi theo tên chính, vì slug sinh từ tên tiếng Việt ra một chuỗi không
    khớp với nguồn nào khác.
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


class AppStoreAdapter(BaseAdapter[list[dict[str, Any]], list[dict[str, Any]]]):
    """`normalize` trả payload thô, việc dựng `Game` để `to_game` lo.

    Ba endpoint trả ba hình dạng khác nhau — RSS đời cũ không hề giống
    search/lookup — nên không có một phép chuẩn hoá chung nào đúng cho cả ba.
    Mỗi hàm công khai tự đọc hình dạng của mình.
    """

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

        if operation == "search":
            payload = await self._get_json(
                SEARCH_URL,
                {
                    "term": params["term"],
                    "country": self._country,
                    "media": "software",
                    "entity": "software",
                    "limit": str(min(params["limit"], SEARCH_LIMIT)),
                },
            )
            return [item for item in (payload or {}).get("results", []) if is_game(item)]

        if operation == "lookup":
            payload = await self._get_json(
                LOOKUP_URL,
                {
                    "id": ",".join(params["ids"]),
                    "country": params["country"],
                    "entity": "software",
                },
            )
            return [item for item in (payload or {}).get("results", []) if is_game(item)]

        if operation == "chart":
            payload = await self._get_json(
                RSS_URL.format(
                    country=self._country,
                    kind=_FEED_KINDS[params["feed"]],
                    limit=min(params["limit"], CHART_LIMIT),
                    genre=GAMES_GENRE_ID,
                )
            )
            return list((payload or {}).get("feed", {}).get("entry", []))

        raise PermanentError(f"thao tác không biết: {operation!r}")

    def normalize(self, raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return raw

    def _entities(self, raw: list[dict[str, Any]]) -> list[Game]:
        out: list[Game] = []
        for result in raw:
            try:
                out.append(to_game(result))
            except PermanentError as exc:
                # Một record hỏng không được làm hỏng cả lô 200.
                logger.warning("bỏ qua record App Store", extra={"error": str(exc)})
        return out

    async def search(self, term: str, *, limit: int = SEARCH_LIMIT) -> list[Game]:
        """Tìm game theo từ khoá ở gian hàng VN — nguồn khám phá chính.

        Payload có cùng hình dạng với `lookup`, đủ ảnh và thể loại, nên không
        cần gọi thêm bước nào.
        """
        return self._entities(
            await self.fetch(endpoint="search", op="search", term=term, limit=limit)
        )

    async def chart_ids(self, feed: Feed, *, limit: int = CHART_LIMIT) -> list[str]:
        """Id game trong một bảng xếp hạng của gian hàng VN.

        Chỉ trả id: payload RSS đời cũ có hình dạng riêng, mà `lookup` thì gộp
        được 200 id một lần nên lấy chi tiết ở đó rẻ hơn viết thêm một phép ánh
        xạ nữa.
        """
        entries = await self.fetch(endpoint=f"chart/{feed}", op="chart", feed=feed, limit=limit)
        ids: list[str] = []
        for entry in entries:
            track_id = (entry.get("id") or {}).get("attributes", {}).get("im:id")
            if track_id:
                ids.append(str(track_id))
        return ids

    async def details(self, ids: list[str], *, country: str | None = None) -> list[Game]:
        raw: list[dict[str, Any]] = []
        for start in range(0, len(ids), LOOKUP_BATCH):
            raw += await self.fetch(
                endpoint="lookup",
                op="lookup",
                ids=ids[start : start + LOOKUP_BATCH],
                country=country or self._country,
            )
        return self._entities(raw)

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
