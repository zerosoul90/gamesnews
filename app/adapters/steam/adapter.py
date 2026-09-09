"""Steam — xương sống catalog thay cho IGDB.

`PHASE-1.md` mục 1 định dùng IGDB, nhưng console developer của Twitch bắt buộc
bật 2FA bằng số điện thoại, mà tài khoản không làm được — xem `PROGRESS.md`.
Steam thế chỗ: nó không phủ mobile (phần đó đã có mục 5 lo) nhưng phủ PC dày
hơn IGDB, và `steam_appid` vốn đã là khoá cầu nối chính của `SCHEMA.md`.

Hai endpoint, hai chế độ xác thực khác hẳn nhau — kiểm bằng tay 2026-09-08:

- `IStoreService/GetAppList/v1` — **cần Steam Web API key**. Endpoint keyless
  cũ `ISteamApps/GetAppList` đã bị Valve gỡ ("Method 'GetAppList' not found in
  interface 'ISteamApps'"), và trong danh sách 27 interface không cần key
  không còn method liệt kê app nào. Lọc ngay tại nguồn bằng `include_*`, nên
  với `include_games=true` và mọi cờ khác false thì ra **184.981 game**, không
  lẫn DLC/phần mềm/video. Lật trang bằng `last_appid`.
- `store.steampowered.com/api/appdetails` — **không cần key**, nhưng
  `~200 request/5 phút mỗi IP` (`CLAUDE.md`) và mỗi lần chỉ một appid.

Chỗ dễ hiểu nhầm nhất: appdetails trả `{"<appid>": {"success": false}}` cho
appid không còn bán, không bán ở VN, hoặc bị bóp tốc độ. Đó **không** phải lỗi
HTTP — mã vẫn là 200. Coi nó là lỗi thì job dừng ngay ở app thứ mấy chục.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any, ClassVar

import httpx

from app.adapters.base import (
    AdapterConfig,
    BaseAdapter,
    PermanentError,
    RateLimit,
    TransientError,
    classify_http_status,
)
from app.models.game import ExternalIds, Game, GameType, Media, ReleaseDate, Titles
from app.services.normalize import slugify

logger = logging.getLogger(__name__)

APP_LIST_URL = "https://api.steampowered.com/IStoreService/GetAppList/v1/"
APP_DETAILS_URL = "https://store.steampowered.com/api/appdetails"

# `CLAUDE.md`: ~200 request/5 phút mỗi IP cho appdetails. Đây là ràng buộc chặt
# nhất của cả hệ thống, và Phase 2 sẽ dùng chung đúng bucket này.
DETAILS_RATE_LIMIT = RateLimit(capacity=200, per_seconds=300.0)

# GetAppList tính theo key (100.000 lượt/ngày), rộng hơn nhiều — nhưng vẫn tách
# bucket riêng để job catalog không ăn mất quota appdetails của job giá.
APP_LIST_RATE_LIMIT = RateLimit(capacity=60, per_seconds=60.0)

APP_LIST_PAGE = 50_000

# `type` của Steam so với `GameType` của ta. Thiếu ở đây (music, video, tool,
# hardware, series, episode...) nghĩa là không đưa vào catalog.
_TYPE_MAP: dict[str, GameType] = {
    "game": "game",
    "dlc": "dlc",
    "demo": "demo",
    "bundle": "bundle",
    "mod": "game",
}

# `release_date.date` phụ thuộc `l=`; luôn gọi với `l=english` để cố định nó.
_DATE_FORMATS = ("%d %b, %Y", "%b %d, %Y", "%d %B, %Y", "%B %d, %Y")


class SteamAppRef:
    """Một dòng của GetAppList: chỉ appid + tên."""

    __slots__ = ("appid", "name")

    def __init__(self, appid: int, name: str) -> None:
        self.appid = appid
        self.name = name


def _release_iso(release: dict[str, Any] | None) -> str | None:
    """ "24 Feb, 2022" -> "2022-02-24". Trả None nếu chưa ra mắt hoặc chỉ có năm.

    Steam ghi ngày sắp ra mắt đủ kiểu ("Q4 2026", "Coming soon"), nên parse
    không được thì để trống — đoán bừa còn tệ hơn.
    """
    if not release or release.get("coming_soon"):
        return None
    raw = str(release.get("date") or "").strip()
    if not raw:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return dt.datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    logger.debug("không đọc được ngày phát hành Steam", extra={"value": raw})
    return None


def _platforms(data: dict[str, Any]) -> list[str]:
    """Steam chia windows/mac/linux; catalog của ta gộp chúng thành "pc".

    Cả ba đều là cùng một bản PC, và người dùng lọc theo "PC" chứ không lọc
    theo hệ điều hành. Khi nào cần tách thì `SCHEMA.md` phải mở rộng trước.
    """
    platforms = data.get("platforms") or {}
    return ["pc"] if any(platforms.values()) else []


def to_game(data: dict[str, Any]) -> Game | None:
    """Payload `appdetails` -> entity `games`. None nghĩa là không phải game.

    Trả None chứ không ném lỗi: danh sách app của Steam lẫn nhạc nền, phần mềm
    dựng phim, phần cứng. Chúng bị bỏ qua là chuyện bình thường, không phải sự
    cố cần retry.
    """
    steam_type = str(data.get("type") or "").lower()
    game_type = _TYPE_MAP.get(steam_type)
    if game_type is None:
        return None

    appid = data.get("steam_appid")
    if appid is None:
        raise PermanentError(f"appdetails thiếu steam_appid: {data.get('name')!r}")

    name = str(data.get("name") or "").strip()
    if not name:
        raise PermanentError(f"appdetails thiếu name: {appid}")

    released = _release_iso(data.get("release_date"))

    return Game(
        slug=slugify(name),
        titles=Titles(primary=name),
        type=game_type,
        external_ids=ExternalIds(steam_appid=int(appid)),
        # Steam là một trong số ít nguồn phân biệt được studio và nhà phát
        # hành, nên ở đây điền được cả hai — khác hẳn hai store mobile.
        developers=[str(x) for x in data.get("developers", []) if x],
        publishers=[str(x) for x in data.get("publishers", []) if x],
        genres=[
            slug
            for genre in data.get("genres", [])
            if (slug := slugify(str(genre.get("description") or "")))
        ],
        platforms=_platforms(data),
        release_dates=(
            [ReleaseDate(region="ww", date=released, platform="pc")] if released else []
        ),
        media=Media(
            cover=data.get("header_image"),
            screenshots=[
                str(shot["path_full"])
                for shot in data.get("screenshots", [])
                if shot.get("path_full")
            ],
        ),
    )


def parent_appid(data: dict[str, Any]) -> int | None:
    """AppID của game cha, nếu đây là DLC.

    `PHASE-1.md` mục 2 xếp "DLC phải trỏ `parent_game`" vào ba chỗ dễ làm sai.
    Steam trả `fullgame: {"appid": "1245620", ...}` — appid ở đây là **chuỗi**.
    """
    full = data.get("fullgame") or {}
    appid = full.get("appid")
    try:
        return int(appid) if appid is not None else None
    except (TypeError, ValueError):
        return None


class SteamCatalogAdapter(BaseAdapter[dict[str, Any], dict[str, Any]]):
    """`normalize` trả payload thô; `to_game` lo phần dựng entity.

    Hai endpoint trả hai hình dạng khác hẳn nhau, và appdetails còn có nhánh
    "không phải game" mà `Game` không biểu diễn được — nên phép chuẩn hoá nằm ở
    hàm ngoài chứ không nhét vào `normalize`.
    """

    source: ClassVar[str] = "steam"

    def __init__(
        self,
        config: AdapterConfig,
        http: httpx.AsyncClient,
        *,
        api_key: str = "",
        country: str = "vn",
    ) -> None:
        super().__init__(config)
        self._http = http
        self._api_key = api_key
        self._country = country

    async def _get_json(self, url: str, params: dict[str, str]) -> Any:
        try:
            response = await self._http.get(url, params=params)
        except httpx.HTTPError as exc:
            raise TransientError(f"không gọi được {url}: {exc!r}") from exc

        error = classify_http_status(response.status_code)
        if error is not None:
            raise error(f"{url} -> {response.status_code}: {response.text[:200]}")
        try:
            return response.json()
        except ValueError as exc:
            raise PermanentError(f"{url} trả về không phải JSON: {exc}") from exc

    async def fetch_raw(self, **params: Any) -> dict[str, Any]:
        operation = params["op"]

        if operation == "app_list":
            if not self._api_key:
                raise PermanentError(
                    "GetAppList cần STEAM_API_KEY; endpoint keyless đã bị Valve gỡ"
                )
            payload = await self._get_json(
                APP_LIST_URL,
                {
                    "key": self._api_key,
                    "max_results": str(APP_LIST_PAGE),
                    "last_appid": str(params["last_appid"]),
                    # Lọc tại nguồn: rẻ hơn nhiều so với tải về rồi bỏ đi.
                    "include_games": "true",
                    "include_dlc": "false",
                    "include_software": "false",
                    "include_videos": "false",
                    "include_hardware": "false",
                },
            )
            response: dict[str, Any] = (payload or {}).get("response", {})
            return response

        if operation == "details":
            appid = params["appid"]
            payload = await self._get_json(
                APP_DETAILS_URL,
                {"appids": str(appid), "cc": self._country, "l": "english"},
            )
            entry: dict[str, Any] = (payload or {}).get(str(appid), {})
            return entry

        if operation == "prices":
            appids = params["appids"]
            if len(appids) > 50:
                raise ValueError("Steam prices endpoint chỉ nhận tối đa 50 appids mỗi lượt")

            payload = await self._get_json(
                APP_DETAILS_URL,
                {
                    "appids": ",".join(str(i) for i in appids),
                    "cc": self._country,
                    "filters": "price_overview",
                },
            )
            return payload or {}

        raise PermanentError(f"thao tác không biết: {operation!r}")

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        return raw

    async def app_list_page(self, last_appid: int = 0) -> tuple[list[SteamAppRef], int | None]:
        """Một trang danh sách game. Trả về (danh sách, last_appid kế tiếp).

        `last_appid` kế tiếp là None khi đã hết — đó là điều kiện dừng, đừng
        dựa vào số phần tử trả về.
        """
        response = await self.fetch(endpoint="app_list", op="app_list", last_appid=last_appid)
        apps = [
            SteamAppRef(int(app["appid"]), str(app.get("name") or ""))
            for app in response.get("apps", [])
            if app.get("appid") is not None
        ]
        next_cursor = response.get("last_appid") if response.get("have_more_results") else None
        return apps, int(next_cursor) if next_cursor is not None else None

    async def details(self, appid: int) -> dict[str, Any] | None:
        """Payload chi tiết, hoặc None nếu Steam trả `success: false`.

        `success: false` đến từ app đã gỡ khỏi cửa hàng, app không bán ở VN,
        hoặc chính ta đang bị bóp tốc độ — mã HTTP vẫn 200. Người gọi phải phân
        biệt được "không có dữ liệu" với "hỏng", nên trả None thay vì ném lỗi.
        """
        entry = await self.fetch(endpoint="appdetails", op="details", appid=appid)
        if not entry.get("success"):
            return None
        data: dict[str, Any] = entry.get("data") or {}
        return data or None

    async def prices(self, appids: list[int]) -> dict[int, dict[str, Any] | None]:
        """Lấy giá cho một lô appids (tối đa 50).

        Trả về dict map appid với payload của Steam (hoặc None nếu success=false hoặc thiếu data).
        """
        if not appids:
            return {}

        payload = await self.fetch(endpoint="appdetails", op="prices", appids=appids)
        result: dict[int, dict[str, Any] | None] = {}
        for appid in appids:
            entry = payload.get(str(appid))
            if not entry or not entry.get("success"):
                result[appid] = None
            else:
                result[appid] = entry.get("data") or {}
        return result
