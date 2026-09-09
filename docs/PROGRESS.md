# PROGRESS.md — Tiến độ

**Phase hiện tại:** Phase 1 — Catalog + Search
**Cập nhật lần cuối:** 2026-09-08

Phase 0 đã đạt toàn bộ checkpoint nghiệm thu. Chỉ còn mục 7 (đăng ký key ngoài)
là việc của người dùng, Phase 1 mới cần tới.

---

## Quyết định cần chốt trước khi code

- [x] Tên dự án chính thức: `gamesnews`
- [x] **Mũi nhọn**: giá VND + đáy lịch sử (giftcode/lịch banner lùi Phase 8)
- [x] **Web framework**: Angular, bắt buộc bật `@angular/ssr`
- [x] Ngôn ngữ nội dung MVP: Việt + Anh
- [x] **Scheduler**: Arq (Redis-backed, async)
- [x] **State management Flutter**: Riverpod
- [ ] Có làm affiliate không → ảnh hưởng quyền dùng Reddit / RAWG API
- [ ] Đăng ký Oracle Cloud Always Free, mua domain

---

## Phase 0 — Nền móng

**Checkpoint:** `docker compose up` khởi động cả 6 service, `/health` xanh cả
4 kho dữ liệu.

- [x] Khởi tạo repo, cấu trúc thư mục theo `CLAUDE.md`
- [x] Skeleton FastAPI: config, logging, health check — chạy thật, `/health`
      trả đúng 503 khi cả bốn kho đều tắt
- [x] `adapters/base.py` — interface chung, token bucket Redis, retry/backoff,
      phân loại lỗi, hook đo quota; kèm `adapters/dummy/` và test
- [x] `ruff`, `mypy --strict`, `pytest` sạch trên máy dev và trên CI
- [x] CI: ruff + mypy + pytest — xanh ở run #1. Có Redis service thật nên 10
      test token bucket chạy thật, không skip
- [x] `docker-compose.yml`: 6 service — `docker compose up` chạy thật, cả 6
      container lên, 3 healthcheck (mongo/redis/meilisearch) đều `healthy`
- [x] Worker Arq — chạy thật, nhận job `ping` qua Redis và trả `pong`
- [x] `/health` nghiệm thu tích hợp: 200 khi đủ 4 kho; tắt Meilisearch → 503
      chỉ đúng service hỏng; tắt Qdrant → vẫn 200, body ghi `degraded`
- [ ] Đăng ký key: Twitch developer (IGDB), Steam Web API — việc của người dùng

---

## Phase 1 — Catalog + Search

**Checkpoint:** `elden ring` / `elden` / `erden ring` / `vong elden` đều ra
đúng game ở vị trí đầu. Catalog ≥ 50.000 game.

- [x] ~~Adapter IGDB~~ → **Adapter Steam** + hai job đồng bộ. IGDB bỏ hẳn:
      Twitch bắt 2FA bằng số điện thoại, tài khoản không làm được
- [x] Collection `games` theo `SCHEMA.md`, index đầy đủ
- [x] Sinh `aliases_normalized` (bỏ dấu, lowercase, chuẩn hoá khoảng trắng)
- [x] Bảng ID mapping + `find_game_by_external_id` — **khung** đã xong; dữ liệu
      thật phải chờ adapter
- [x] Bổ sung game mobile từ Google Play + App Store
- [x] Index Meilisearch + cấu hình tiếng Việt
- [x] API tìm kiếm + facet
- [x] Trang admin xem/sửa entity

---

## Phase 2 — Giá & Deal

**Checkpoint:** theo dõi ổn định 5.000 game hot; biểu đồ giá 30 ngày khớp khi
đối chiếu tay 20 game mẫu; không có dòng history trùng.

- [x] Adapter Steam appdetails (cc=vn) + token bucket tôn trọng 200 req/5 phút
- [x] Adapter Epic (GraphQL + freeGamesPromotions) (Đã làm phần freeGamesPromotions)
- [ ] Adapter GOG, CheapShark
- [x] Scheduler phân tầng hot / ấm / lạnh
- [x] `price_current` + `price_history` (chỉ ghi khi giá đổi)
- [x] Tính `lowest_ever`, cờ đang ở đáy
- [x] Cờ khoá khu vực VN
- [x] API: giá theo game, danh sách deal, free tuần này

---

## Phase 3 — Người dùng & Thông báo

**Checkpoint:** push đến trong 15 phút khi giá chạm ngưỡng; không bao giờ báo
giảm giá game đã sở hữu.

- [x] Auth + Steam OpenID
- [x] Import `GetOwnedGames` + `GetWishlist` (tra ngược tên từ appid)
- [ ] Hướng dẫn có ảnh để đặt profile Public + tự kiểm tra lại (đã làm API ném lỗi chuẩn 403 PROFILE_IS_PRIVATE)
- [x] Màn hình tick nhanh game free Epic theo tuần (đã thêm API bulk insert)
- [x] Follow game / series / studio / nền tảng
- [x] Ngưỡng cảnh báo linh hoạt (below_price, discount_pct, historical_low)
- [x] FCM: digest, giờ im lặng, bật/tắt từng loại (Gatekeeper)

---

## Phase 4 — Web công khai & SEO

**Checkpoint:** Lighthouse SEO ≥ 90; tắt JS vẫn đọc đủ nội dung; thẻ chia sẻ
render đúng trên Facebook và Zalo.

- [x] Chốt framework, dựng SSR (Angular 18)
- [x] Trang game trả lời sẵn 4 câu hỏi dài tiếng Việt (GameComponent tĩnh)
- [x] Trang deal, trang free tuần này (DealComponent, FreeComponent)
- [x] Thẻ chia sẻ dạng ảnh sinh phía server (Pillow FastAPI /api/v1/og-image)
- [x] Sitemap, structured data, i18n route (Meta service Angular)
- [x] Umami self-host (Thêm Postgres & Umami vào Docker Compose)

---

## Phase 5 — Mobile

- [x] Khung app (Flutter, Riverpod, go_router)
- [x] Dựng sơ đồ luồng các màn hình chính (Điều hướng Bottom Bar)
- [x] Tích hợp API Client, Deep link, FCM push
- [x] Widget Android / Live Activity iOS
- [x] Apple Developer + Google Play Console

---

## Phase 6 — Tin tức & dịch

**Checkpoint:** gắn entity tự động ≥ 85%; tin quốc tế lên feed tiếng Việt
trong 2 giờ.

- [x] Quản lý nguồn + 10–15 RSS
- [x] Khử trùng lặp simhash
- [x] Gắn entity 3 tầng + hàng đợi duyệt
- [x] Vòng phản hồi sinh alias từ mỗi lần duyệt tay
- [x] LLM adapter tóm tắt + dịch

---

## Phase 7 — Chỉ số hot & Streamer

**Checkpoint:** bảng "Đang tăng mạnh" không bị game top thường trực chiếm chỗ;
push streamer live trong 60 giây.

- [x] Thu thập CCU, most played, top sellers cc=vn, reviews
- [x] Twitch Get Streams + EventSub
- [x] YouTube WebSub + job gia hạn subscription
- [x] Chuẩn hoá percentile, hai bảng hot/rising
- [x] Rollup time-series
- [x] Danh sách streamer Việt (curate tay)

---

## Phase 8 — Cộng đồng & Giftcode

- [x] Đánh giá + điểm người dùng (ẩn dưới 20 lượt), chống review bombing
- [x] Giftcode + lịch banner mobile
- [x] Mở hàng đợi duyệt cho cộng đồng, badge
- [x] Thống kê thư viện + tổng kết cuối năm

---

## Nhật ký

<!-- Ghi ngắn: ngày | việc đã xong | quyết định phát sinh -->

### 2026-09-07 — Phase 0, mục 1-7

Xong khung dự án. `ruff` + `mypy --strict` + `pytest` sạch (28 pass, 10 skip).

**Quyết định phát sinh, khác hoặc thêm so với tài liệu:**

- **uv + `uv.lock`** làm trình quản lý phụ thuộc. Docker cài bằng
  `uv sync --frozen` nên image và máy dev luôn khớp nhau.
- **`RateLimiter` là Protocol**, `RedisTokenBucket` chỉ là một bản cài. Nhờ
  vậy test adapter chạy được không cần Redis.
- **Token bucket viết bằng Lua** chạy nguyên tử trong Redis. Tách đọc–tính–ghi
  ra ngoài thì hai worker cùng đọc một trạng thái và cùng tưởng còn token.
  Mặc định lấy đồng hồ của Redis, không lấy đồng hồ tiến trình, vì worker và
  API có thể nằm ở hai máy.
- **Retry cũng tiêu token.** Mỗi lần thử là một request thật; không trừ thì
  bucket không phản ánh đúng quota đã dùng.
- **Lỗi lạ chưa phân loại bị coi là vĩnh viễn.** Retry mù một lỗi lập trình
  chỉ tốn quota Steam.
- **`core/db.py` giữ cả Redis và httpx**, không chỉ Motor như tài liệu ghi.
  Ba client cùng vòng đời, tách ra chỉ làm lifespan phải quản nhiều chỗ.
- **`redis --appendonly yes`**: Arq giữ hàng đợi trong Redis, không bật AOF là
  mất job đang chờ khi restart.
- **Meilisearch chạy `MEILI_ENV=production` ngay từ dev**, nên bắt buộc có
  `MEILI_MASTER_KEY`. Dev và prod không lệch nhau.
- **Qdrant không có healthcheck** trong compose (image không kèm curl/wget);
  `app` chỉ chờ `service_started`. Khớp với việc Qdrant chưa bắt buộc.
- **Ping Meilisearch/Qdrant bằng httpx**, chưa thêm SDK riêng của hai kho này.
- **`REQUIRE_REDIS=1` trên CI**: test rate limiter không được phép skip. Không
  có chốt này thì Redis service hỏng là CI vẫn xanh dù phần logic quan trọng
  nhất chưa được kiểm.

**Chưa nghiệm thu được:**

- 3 checkpoint cần Docker (`docker compose up`, worker nhận job, tắt từng
  service xem `/health`). Máy dev chưa cài Docker.
- `/health` đã có test đơn vị cho cả ba nhánh 200/degraded/503, nhưng đó không
  thay được test tích hợp thật.

### 2026-09-07 — CI run #1 xanh

Commit `0ec3144`, chạy 46 giây, cả hai job đều success.

- `lint-test`: ruff, mypy, pytest đều xanh. **10 test token bucket đã chạy
  thật trên Redis**, suy ra từ `REQUIRE_REDIS=1` — nếu Redis service không lên
  hoặc test skip thì `pytest.fail` đã làm step đỏ. Nghĩa là script Lua đúng:
  bucket dùng chung giữa hai client, nạp lại theo thời gian, không tích quá
  capacity, trần chờ, đồng hồ Redis.
- `compose`: `docker compose config` hợp lệ. Mới là cú pháp, chưa chứng minh
  service khởi động được — checkpoint `docker compose up` vẫn còn nợ.

### 2026-09-07 — Trả nốt 3 checkpoint Docker của Phase 0

Máy dev đã có Docker (engine 29.6.1). Ba mục ghi nợ ở entry đầu ngày nay giờ
nghiệm thu được, **không phải sửa dòng code nào** — compose và worker chạy đúng
ngay lần `up` đầu tiên.

- **`docker compose up -d --build`**: cả 6 service lên. `mongo`, `redis`,
  `meilisearch` báo `healthy`; `qdrant` chỉ `running` vì cố ý không có
  healthcheck; `app` và `worker` chờ đúng thứ tự `depends_on` rồi mới khởi
  động.
- **Worker Arq nhận job thật**: enqueue `ping` từ container `app` qua Redis,
  worker trả `'pong'`. Log worker cho thấy `job_id` được dùng làm `request_id`
  — đúng ý đồ `on_job_start`.
- **`/health` ba nhánh, kiểm bằng cách tắt service thật:**

  | Kịch bản | HTTP | `status` | Ghi nhận |
  |---|---|---|---|
  | Đủ 4 kho | 200 | `ok` | latency mỗi kho 3–13 ms |
  | Tắt Meilisearch | 503 | `unhealthy` | chỉ `meilisearch` là `down` |
  | Tắt Qdrant | 200 | `degraded` | `qdrant.required: false` |

**Quan sát, chưa sửa:**

- Khi một kho chết, `/health` mất đúng `HEALTH_TIMEOUT_SECONDS` (2 s) mới trả
  lời, vì `_probe` chạy hết trần timeout. Bốn probe chạy song song nên 2 s là
  trần chung, không cộng dồn. Chấp nhận được với health check, nhưng nếu sau
  này gắn vào load balancer có timeout ngắn hơn thì phải hạ số này.
- `git status` sạch sau toàn bộ quá trình: `.env` (có `MEILI_MASTER_KEY` thật)
  nằm ngoài index đúng như `.gitignore` quy định.

### 2026-09-07 — Phase 1: xương sống catalog + tìm kiếm

Chưa có key Twitch nên mục 1 (adapter IGDB) và mục 5 (scraper mobile) để lại.
Làm mục 2, 3, 4, 6, 7 trước — `SCHEMA.md` đã định nghĩa sẵn document `games`
nên thứ bị chặn chỉ là tầng ánh xạ field của riêng IGDB, không phải schema.

Mục 3 hoá ra đã xong từ ba commit trước đó, chỉ bổ sung `slugify`.

**Quyết định phát sinh:**

- **`partialFilterExpression`, không phải `sparse`, cho các ID ngoài.** Đa số
  game không bán trên Steam nên `external_ids.steam_appid` là null trên phần
  lớn document. `sparse` chỉ bỏ qua document *thiếu hẳn* field; ở đây field có
  mặt với giá trị null, mà Mongo coi nhiều null là trùng nhau → index unique
  đổ ngay ở document thứ hai. Có test riêng cho chốt này.
- **`content_hash` quyết định có ghi hay không.** Upsert thẳng thì mỗi lần
  chạy job, cả catalog bị ghi đè và `updated_at` nhảy hết dù dữ liệu y nguyên.
  Hệ quả là job đồng bộ delta ở mục 6 mất căn cứ — "delta" thành "toàn bộ".
  `updated_at` và `content_hash` cố ý **không** nằm trong model `Game`, để hash
  chỉ băm phần nội dung.
- **Định danh entity bằng ID của nguồn, không bằng slug.** Slug đổi được.
- **`type_rank:asc` đặt SAU `exactness` trong ranking rules.** Đặt trước thì nó
  thắng cả độ khớp: gõ đúng tên một DLC vẫn bị game cha đẩy lên đầu. Đặt cuối
  thì nó chỉ phá thế hoà — đúng lúc cần và chỉ lúc đó. Có test cho cả hai chiều.
- **Meilisearch báo lỗi trong *task*, không bằng mã HTTP.** Xoá một index không
  tồn tại vẫn trả 202 kèm `taskUid`, rồi task đó mới `failed`. Bản đầu kiểm mã
  404 nên job chạy lần hai là đỏ. `wait_for_task` giờ nhận `ignore_error_codes`.
- **Alias không được chép tay vào fixture** mà sinh qua `with_aliases`, đúng
  đường job đồng bộ thật sẽ đi. Nhờ vậy test tìm kiếm kiểm luôn `normalize_vi`.
- **CI có thêm Mongo và Meilisearch thật**, kèm `REQUIRE_MONGO` /
  `REQUIRE_MEILI` để test không được phép skip — cùng lý lẽ với `REQUIRE_REDIS`.
- **Master key Meilisearch chỉ ở phía server.** Client không nói thẳng với
  Meilisearch, mọi truy vấn đi qua `/search` của ta.

**Đã nghiệm thu (174 test xanh, ruff + mypy --strict sạch):**

| Checkpoint PHASE-1 | Trạng thái |
|---|---|
| `elden ring` / `elden` / `erden ring` / `vong elden` ra đúng game đầu bảng | xanh |
| `エルデンリング` ra đúng game | xanh |
| Game mobile phổ biến ở VN (Liên Quân) | xanh |
| Lọc platform + năm cho facet count đúng | xanh |
| Chạy lại job đồng bộ không sinh entity trùng | xanh (`unchanged: 26`) |
| Test `normalize_vi` | xanh |
| Catalog ≥ 50.000 game | **chưa** — cần adapter IGDB |

Kiểm cả trên app thật qua HTTP, không chỉ trong test: `đế chế` ra Age of
Empires II, `liên quân` ra Arena of Valor, `final fantasy 7 remake` ra bản
`VII`, `per_page` ngoài khoảng trả 422.

**Nợ lại:** catalog hiện chỉ có 26 game fixture. Bộ này đủ để chứng minh chất
lượng tìm kiếm và ranking, **không** phải dữ liệu thật — nó nằm trong
`tests/fixtures/`, không phải nguồn seed cho sản phẩm.

**CI xanh ở run thứ ba — 174 passed, 0 skipped.** Hai lần đỏ đầu đều là lỗi
cấu hình service, đáng ghi vì dễ gặp lại:

1. `MEILI_MASTER_KEY` trên CI chỉ 11 byte. `MEILI_ENV=production` đòi tối thiểu
   16 byte, nên container chết ngay lúc khởi động.
2. Healthcheck Mongo không bao giờ xanh. `options:` của GitHub Actions là một
   **chuỗi**, Docker chạy nó qua `sh -c`; còn `docker-compose.yml` dùng **mảng
   exec**, không qua shell. Cùng một lệnh `mongosh --eval db.adminCommand(...)`
   chạy tốt ở máy dev nhưng trên CI thì cặp ngoặc đơn bị shell đọc như cú pháp
   subshell: `sh: 1: Syntax error: "(" unexpected`. Phải bọc cả biểu thức JS
   trong nháy đơn.

Điều đáng nhớ: `docker compose config` hợp lệ và compose chạy được ở máy dev
**không** bảo đảm cùng lệnh đó chạy được trong service container của CI.

### 2026-09-08 — Phase 1 mục 8: admin entity

Làm mục 8 trước mục 5 dù tài liệu đánh số ngược lại. Lý do: mục 5 sẽ đẩy vào
catalog những entity mobile định danh bằng `google_play`/`app_store`, và chính
chúng sau này trùng với entity IGDB của cùng một game. Có công cụ gộp trước thì
lúc đó dọn được; làm ngược lại thì nợ chồng lên.

**Quyết định phát sinh:**

- **Trang HTML server-render bằng Jinja2, không phải Angular.** Phase 4 mới tới
  web; dựng SPA chỉ để sửa alias là vượt phạm vi. Hai mặt cùng một nghiệp vụ:
  `/admin/api/...` trả JSON (script và test dùng), `/admin/...` là trang bấm
  được.
- **Gộp phải mang theo `external_ids`.** Đây là nửa quan trọng nhất của thao
  tác. Sau khi gộp, job đồng bộ của nguồn bên bị gộp vẫn chạy với ID cũ của nó.
  ID đó không nằm trên entity còn lại thì `upsert_game` không tìm thấy gì và
  insert lại đúng entity vừa xoá — công gộp tay mất sạch sau một đêm. Có test
  đúng kịch bản đó.
- **Hai ID khác nhau ở cùng một nguồn thì TỪ CHỐI gộp (409).** Hai Steam AppID
  khác nhau gần như luôn là hai sản phẩm khác nhau. Gộp bừa thì Phase 2 lấy giá
  game này gắn cho game kia — sai kiểu rất khó phát hiện.
- **Xoá bên bị gộp trước, ghi bên giữ lại sau.** Index unique một phần trên
  `external_ids` chặn ngay nếu gán ID của bên bị gộp cho bên giữ lại trong khi
  document cũ còn đó. Mongo standalone không có transaction, nên bước ghi hỏng
  thì insert lại document vừa xoá.
- **DLC không được thành mồ côi.** Gộp xong phải trỏ lại `parent_game` của mọi
  DLC đang trỏ vào entity bị xoá.
- **Alias sửa tay là THÊM, không phải THAY**, và đi qua đúng `with_aliases` mà
  job đồng bộ dùng. Nhờ vậy `aliases_normalized` không bao giờ lệch pha với
  `aliases`, và admin xoá sạch ô nhập cũng không mất tên chính của game.
- **Sửa alias y hệt thì không đụng `updated_at`** — cùng lý lẽ với
  `content_hash`: `updated_at` nhảy vô cớ là job reindex delta phải đẩy lại một
  entity không đổi gì.
- **Tìm entity trong admin truy thẳng Mongo, không qua Meilisearch.** Lý do hay
  phải mở trang admin nhất lại chính là "game này tìm không ra"; dùng Meili ở
  đây thì đúng lúc cần nhất nó lại không giúp được.
- **Mọi thao tác ghi đẩy sang Meilisearch ngay trong request**, không đợi job
  delta. Admin sửa xong tìm lại thấy dữ liệu cũ sẽ tưởng lần đầu không ăn và
  sửa thêm lần nữa.
- **`/admin` mặc định ĐÓNG khi thiếu `ADMIN_TOKEN`** (503). Một trang sửa được
  cả catalog mà không có mật khẩu còn tệ hơn nhiều so với việc admin tạm thời
  không vào được. Token đi vào cookie `HttpOnly` + `SameSite=Strict` qua form
  đăng nhập, **không** qua query string — query string vào log của mọi proxy
  trên đường và vào lịch sử trình duyệt.
- Thêm hai phụ thuộc: `jinja2` và `python-multipart` (FastAPI cần nó để đọc
  form HTML).

**Đã nghiệm thu: CI xanh, 204 test, 0 skip.** Máy dev hiện tại không có Docker
nên 32 test mới cần Mongo đều skip ở local — CI là nơi duy nhất chúng chạy
thật. Kiểm bù được ở local: render cả bốn template ngoài HTTP (autoescape chặn
`<script>` trong tên game), OpenAPI dựng đủ 10 route `/admin`, ruff + mypy
--strict sạch.

Hai lần CI đỏ đầu đều là lỗi **trong test**, không phải trong code — và đáng
ghi vì cùng một kiểu: test tự mâu thuẫn với chính luật mà nó đang kiểm.

1. Test "DLC không mồ côi" dựng hai entity cùng có `igdb` id khác nhau, tức là
   rơi đúng vào luật từ chối gộp, chết trước khi tới phần cần kiểm.
2. Test xung đột 409 gọi `insert()` với key mặc định `igdb` trong khi game chỉ
   có `steam_appid`, nên `upsert_game` ném `ValueError` trước cả khi chạm API.

**Đọc được CI hỏng ở đâu mà không đăng nhập GitHub.** Máy dev không đăng nhập
được GitHub, mà log của Actions thì đòi đăng nhập — kể cả với repo public, và
trang Summary cũng vậy. Đường đi được: `::error::` sinh ra annotation, và
`/repos/{owner}/{repo}/check-runs/{id}/annotations` trả về **không cần token**.
CI giờ đăng phần cuối output pytest ra cả Summary lẫn annotation
(`.github/scripts/annotate_pytest.py`), chia mẩu 2500 ký tự vì GitHub cắt bớt
message dài.

Một cái bẫy nữa, mất một lượt CI: nhúng heredoc Python vào block scalar YAML
của `ci.yml`. Ký tự xuống dòng trong chuỗi thành xuống dòng thật, block scalar
đứt, YAML không parse được — **workflow không chạy job nào nhưng run vẫn hiện
là `failure`**, nhìn qua tưởng test đỏ. Dấu hiệu nhận ra: `/jobs` trả
`total_count: 0`. Vì vậy script annotate nằm ở file riêng, không nhúng vào
YAML.

**Còn nợ của Phase 1:** mục 1 (adapter IGDB) vẫn chặn vì thiếu key Twitch, kéo
theo checkpoint "catalog ≥ 50.000 game". Mục 5 (catalog mobile) chưa làm.

### 2026-09-08 — Phase 1 mục 5: catalog mobile

Hai adapter, hai job Arq tách biệt. **CI xanh, 233 test, 0 skip.**

Điều đáng giá nhất của mục này không nằm trong code mà ở chỗ **chạy thử thật
hai nguồn**: bốn lỗi dưới đây không test nào bắt được, vì fixture ban đầu do
tôi tự dựng chứ không ghi lại từ payload thật. Bài học: fixture của nguồn ngoài
phải chép từ phản hồi thật, đừng viết theo trí nhớ.

**App Store — API marketing v2 không dùng được cho game.**

| Thử | Kết quả thật |
|---|---|
| `limit=200` | 500 (chỉ 10/20/25/50/100 chạy) — mà 500 bị xếp là lỗi tạm thời nên còn bị retry ba lần |
| `top-grossing`, `top-free-ipad`, `top-free-games` | 404, không tồn tại |
| Lookup 100 mục đầu bảng "apps" VN | **0 game** — toàn Finance/Photo/Business |

Bảng "apps" của v2 loại hẳn game, và v2 không có bảng games nào. Phải quay về
endpoint RSS đời cũ `.../rss/{kind}/limit=N/genre=6014/json` — cái **duy nhất**
lọc được theo thể loại. Chạy thật: 100 top-free + 98 top-paid + 100
top-grossing, đầu bảng Block Blast!, Coin Master, Stardew Valley.

**Nguồn khám phá chính là iTunes Search, không phải bảng xếp hạng.** Mỗi từ
khoá trả ~150 kết quả, hầu hết là game, payload đủ dựng entity luôn. Đo thật:
bảng xếp hạng + 6/28 từ khoá đã ra **1008 game duy nhất**, đúng thị trường VN
(Liên Quân, Free Fire, Roblox VN, FC Mobile VN, Thiên Long Bát Bộ VNG).

**Google Play — thư viện đang vỡ một phần**, đúng chỗ `DATA-SOURCES.md` cảnh
báo "dễ vỡ, cần giám sát":

- Kết quả `search` **không có `genreId`**, nên không lọc game ở bước tìm được.
  Việc lọc dời xuống `detail`, nơi payload `app()` có trường đó — cái giá là
  phải gọi `app()` cho cả app không phải game rồi mới loại được nó.
- Hit **đầu bảng** của `search` trả `appId: None`: Play dựng thẻ đầu tiên khác
  các thẻ còn lại và thư viện không bóc được. Tìm "Liên Quân Mobile" thì 4/5
  kết quả có appId, riêng cái đầu thì không. Bỏ qua hit đó và **ghi log số hit
  rơi**, để còn thấy khi nó vỡ thêm.
- `app()` vẫn chạy đủ trường, kể cả `released` bản tiếng Anh parse được.
- Thư viện đồng bộ nên mọi lời gọi đi qua `asyncio.to_thread`; hai hàm của nó
  tiêm qua constructor để test không bao giờ ra Internet.

**Quyết định phát sinh:**

- **App Store dùng API chính thức của Apple, không dùng thư viện scraper** —
  lệch khỏi `DATA-SOURCES.md`, đã hỏi và được duyệt. Search + lookup + RSS đều
  miễn phí, không key, và lookup gộp được 200 id một lần gọi.
- **Job store này không được ghi đè dữ liệu của store kia.** Đây là cái bẫy
  chính. Một entity đã ghép từ hai store, tới lượt job Play chạy mà `$set` cả
  document thì `external_ids.app_store`, platform `ios` và ảnh iOS biến mất —
  rồi lượt sau job App Store ghi đè ngược. Hai job giẫm chân nhau vô tận mà lần
  nào cũng báo "thành công". Vì vậy mọi lần ghi lại đều qua `merge_content` với
  **bên mới làm bên giữ lại**: dữ liệu mới thắng ở chỗ nó có, entity cũ bù vào
  chỗ trống. Có test riêng cho đúng kịch bản đó.
- **Luật ghép entity hai store cố ý chặt**: phải khớp cả tên chuẩn hoá lẫn nhà
  phát hành chuẩn hoá. Cặp bỏ sót thì nhìn thấy được và gộp tay bằng trang
  admin của mục 8; cặp ghép nhầm thì im lặng và hỏng lâu dài. Nghiệm thu trên
  dữ liệu thật: iOS và Play đều ghi "Garena Liên Quân Mobile" / "Garena Mobile
  Private" → ghép đúng.
- **Luật gộp chuyển từ `services/admin.py` sang `services/catalog.py`**, vì giờ
  có hai đường cùng cần nó: người bấm nút gộp, và job mobile.
- **Slug đi theo tên quốc tế.** Slug sinh từ tên tiếng Việt ra chuỗi không khớp
  với nguồn nào khác. Trùng slug thì thêm hậu tố nền tảng rồi mới tới số đếm —
  store mobile đầy game trùng tên ("Sudoku", "Ludo").
- **`publishers` chứ không phải `developers`.** Cả hai store chỉ lộ tên tài
  khoản bán, tức nhà phát hành; ai thật sự làm ra game thì store không nói.
  Chép sang `developers` cho đầy là bịa.
- **Thể loại lấy nguyên phân loại của store** (`slugify`), không ép về bộ thể
  loại trong fixture. Khi có IGDB thì đó mới là nguồn thể loại chuẩn.

**Chưa làm / hạn chế đã biết:**

- Job chưa chạy thật hết một lượt vào Mongo: máy dev không có Docker. Từng mảnh
  đã chạy thật với nguồn ngoài, phần ghi xuống Mongo thì CI kiểm.
- `is_live_service` luôn False cho game mobile. Store không nói, mà đoán theo
  IAP thì sai nhiều hơn đúng — để IGDB hoặc duyệt tay điền.
- Ghép chéo hai store sẽ bỏ sót nhiều cặp, vì hai store hay ghi tên nhà phát
  hành khác nhau ("Garena Mobile Private" so với "GARENA ONLINE PRIVATE
  LIMITED"). Đây là lựa chọn có chủ ý, không phải lỗi.

### 2026-09-08 — Bỏ IGDB, Steam làm xương sống catalog

**Quyết định lớn nhất của phase này, và không phải do kỹ thuật.** Console
developer của Twitch bắt buộc bật 2FA bằng số điện thoại mới cho tạo app; tài
khoản không làm được, nên IGDB mất hẳn — không có đường vòng nào.

Đã khảo sát và **kiểm thật** bốn nguồn thay thế trước khi chọn:

| Nguồn | Key | Kết quả đo thật |
|---|---|---|
| `ISteamApps/GetAppList` (keyless, có trong DATA-SOURCES) | không | **đã bị Valve gỡ** — "Method 'GetAppList' not found" |
| `IStoreService/GetAppList/v1` | Steam Web API key | **184.981 game**, lọc sẵn tại nguồn |
| Wikidata SPARQL | không | 128.407 game có sẵn Steam AppID |
| SteamSpy | không | 1.000 game/trang |
| Steam `featuredcategories` | không | chỉ 66 app — quá nhỏ |

Chọn Steam có key. Người dùng lấy được key (Steam chỉ đòi tài khoản đã mua ≥ 5
USD, không đòi 2FA điện thoại), và nó mở luôn Phase 3.

**Ba chốt đã kiểm bằng tay, ghi lại vì tài liệu trên mạng còn đầy hướng dẫn cũ:**

1. Endpoint keyless liệt kê app **không còn tồn tại**. Trong 27 interface không
   cần key cũng không còn method nào làm việc đó.
2. `appdetails` trả `success: false` kèm **HTTP 200** — với app đã gỡ, app
   không bán ở VN, hoặc khi bị bóp tốc độ (gặp thật lúc ghi fixture: gọi vài
   lần liên tiếp là mọi appid đều false, chờ 60 giây thì bình thường lại). Coi
   nó là lỗi thì job dừng ngay ở app thứ mấy chục.
3. `fullgame.appid` của DLC là **chuỗi**, không phải số. Quên ép kiểu thì tra
   ngược game cha trượt hết mà không báo lỗi gì.

**Quyết định phát sinh:**

- **Sổ công việc `steam_apps` riêng, không đổ 185k app thô vào `games`.** Ở
  bước danh sách chưa biết mục nào thật sự là game — chỉ `appdetails` mới nói
  được `type`. Đổ thẳng thì catalog có 185k entity chưa xác minh và `type` mặc
  định thành "game" cho cả nhạc nền; đúng cái sai mà `PHASE-1.md` cảnh báo là
  "sai ở đây thì mọi phase sau đều hỏng".
- **Hai job tách nhau vì nhịp khác hẳn.** Lấy danh sách xong trong một phút;
  bồi chi tiết 185k app ở mức ~57.600 lượt/ngày mất **vài ngày**. Job thứ hai
  chạy từng lô 200 (đúng trần 5 phút) và nối tiếp được sau khi worker restart —
  nên trạng thái phải nằm trong Mongo, không trong bộ nhớ tiến trình.
- **Hai bucket rate limit riêng** cho GetAppList và appdetails: job catalog
  không được ăn mất quota appdetails mà Phase 2 cần để lấy giá.
- **windows/mac/linux gộp thành `pc`.** Cả ba là cùng một bản PC và người dùng
  lọc theo "PC", không lọc theo hệ điều hành.
- `services/mobile_catalog.py` đổi tên thành `services/ingest.py` — giờ Steam
  cũng đi qua đúng đường ghi đó.

**Mất gì khi bỏ IGDB** (phải bù ở phase sau, đã ghi vào `PHASE-1.md`):

- **alternative names** — nguồn alias đã tính trước trong kế hoạch. Đây là
  thiệt hại lớn nhất, vì chất lượng tìm kiếm phụ thuộc vào alias.
- **ngày phát hành tách theo region + platform** — Steam chỉ có một ngày.

**Nghiệm thu thật qua httpx với key thật:** lật trang đúng (50.000 mục/trang,
cursor `last_appid`), ELDEN RING / Counter-Strike 2 / Dota 2 / Stardew Valley
map đủ trường, DLC Shadow of the Erdtree nhận đúng `type=dlc` và nối được về
game cha. **CI xanh.**

**Chưa chạy hết một lượt thật vào Mongo** — máy dev không có Docker. Checkpoint
"catalog ≥ 50.000 game" vì vậy vẫn chưa đóng được, dù nguồn đã chứng minh có
184.981 game: còn thiếu đúng một lượt chạy job trên máy có Docker.

---

## Đang chặn

**Không còn gì chặn Phase 1.** Steam Web API key đã có (2026-09-08), thay chỗ
IGDB. Bảng dưới là hiện trạng key ngoài:

| Biến | Trạng thái | Dùng cho |
|---|---|---|
| `STEAM_API_KEY` | **đã có** | `IStoreService/GetAppList` — danh sách 184.981 game. Phase 3 (thư viện người dùng) cũng dùng key này |
| `TWITCH_CLIENT_ID` / `TWITCH_CLIENT_SECRET` | **lấy không được** | IGDB (đã bỏ) và **Phase 7 — streamer Twitch, phần này vẫn chặn** |

Console developer của Twitch bắt buộc bật 2FA bằng số điện thoại. Không có
đường vòng, nên tới Phase 7 phải quyết định lại: hoặc chấp nhận bật 2FA, hoặc
bỏ mảng streamer Twitch và chỉ làm YouTube.

`appdetails`, iTunes API và Google Play đều **không cần key**.

> **Việc cần làm của người dùng:** key Steam đã bị dán vào hội thoại nên coi
> như lộ. Vào <https://steamcommunity.com/dev/apikey>, bấm *Revoke* rồi tạo
> key mới, và cập nhật `STEAM_API_KEY` trong `.env`.

### 2026-09-08 — Phase 2: Hệ thống giá & Deal

Hoàn thành cơ bản kiến trúc lấy giá từ Steam và lấy Game Free từ Epic Games. **Lưu ý quan trọng được phát hiện thực tế đo ngày 2026-09-08 làm thay đổi thiết kế so với tài liệu gốc:**

- **Endpoint `filters=price_overview` có thể gộp 50 appid mỗi lượt gọi**, thay vì 1 appid. Giới hạn 200 req/5 phút vẫn giữ nguyên nhưng năng suất thật là 10.000 game / 5 phút (khoảng 2.88 triệu lượt quét / ngày). Quá đủ để quét catalog mà không lo cạn hạn mức, tuy vậy gửi lố 50 id sẽ bị cắt im lặng (không báo lỗi).
- **Tranh chấp Quota chung IP:** Job `sync_steam_details` (Phase 1) và job `sync_steam_prices` đều gọi endpoint `appdetails`. Để giải quyết, hai job này đang dùng chung 1 `RedisTokenBucket` duy nhất (có khóa là `steam_appdetails`). Code lua nguyên tử trên Redis tự điều tiết nhịp.
- **Game Free và Game Khóa vùng trả kết quả giống hệt nhau:** `success: true` nhưng thiếu hẳn `price_overview`. Job xử lý phải check `genres` để cắm cờ `region_locked_vn` một cách chính xác thay vì sinh giá rác.
- **Giá VND bị nhân 100:** Steam trả giá là giá trị int lớn (ví dụ 990.000.000 cho 990.000đ). Luôn phải chia 100 trước khi ghi `price_initial` và `price_final` vào hệ thống.

Cơ chế lưu `price_history` đã được áp dụng logic check giá delta (chỉ append khi `price_final` hoặc `discount_percent` có thay đổi so với `price_current`).

**Ghi chú:** Do hạn chế môi trường ảo của AI không cài được Docker và khởi tạo được MongoDB/Redis, checkpoint "Theo dõi ổn định 5000 game hot suốt 48h..." và chạy test đối chiếu với Steam thực tế cần User chủ động verify ở môi trường dev.

### 2026-09-08 — Phase 3 (Part 1): Auth & Thư viện người dùng

Hoàn thành cụm tính năng nền tảng cho User:
- **Xác thực qua Steam OpenID**: Xây dựng luồng đăng nhập callback trực tiếp tới máy chủ Steam để lấy `SteamID64` an toàn, sau đó hệ thống tự cấp và quản lý phiên bằng `JWT`.
- **Đồng bộ thư viện & Xử lý Private Profile**:
  - Dùng `IPlayerService/GetOwnedGames/v1/` để lấy danh sách game người dùng sở hữu. Tránh lỗi ném 403 không rõ ràng, adapter đã tự bắt payload `{"response": {}}` của Steam khi user ẩn game, sau đó chủ động throw `PrivateProfileError` (trả về lỗi HTTP 403 cụ thể `PROFILE_IS_PRIVATE` cho frontend hướng dẫn người dùng tự mở profile).
  - Áp dụng logic đối soát `appid` lấy từ thư viện Steam với catalog nội bộ; bỏ qua các game rác/phần mềm không có trong `games` collection. Thực hiện thao tác thay máu toàn bộ collection `user_library` cho một người dùng nhanh chóng bằng `DeleteMany` kết hợp `InsertMany`.
- **Tuân thủ Quyền riêng tư**: API `DELETE /api/v1/user/library` dọn dẹp sạch sẽ lịch sử của user khi được yêu cầu.

### 2026-09-08 — Phase 3 (Part 2): Alerts & Notification Gatekeeper

Hoàn thành hệ thống Cảnh báo (Alerts) và Thông báo đẩy (FCM Push):
- **API Mở rộng**: 
  - `POST /api/v1/user/library/epic/bulk`: Hỗ trợ frontend dựng tính năng tick hàng loạt game free của Epic Games theo dải thời gian.
  - Các API Follows và Alerts cho phép định nghĩa các rule `below_price`, `discount_pct`, và `historical_low`.
- **Tối ưu RAM thay vì tạo Job rời**: Thay vì viết một job Arq chạy định kỳ để soi lại giá, hệ thống tận dụng luôn hàm `record_prices` của Phase 2. Khi phát hiện giá `new_price` thấp hơn `old_price` hoặc có % giảm giá, hệ thống sẽ gom các game đó lại và query DB xem có ai đang Alert nó không. Nếu có, trigger Push ngay lập tức.
- **Notification Gatekeeper (Chống Spam)**: `app/services/notification.py` chặn đứng các luồng FCM rác thông qua 3 màng lọc:
  1. Kênh đó có bị user tắt không?
  2. Game đó user **đã sở hữu chưa**? (Kiểm tra chéo với `user_library`).
  3. Có đang nằm trong `quiet_hours` (Giờ đi ngủ) không?
- **Digest Job**: Nếu dính giờ im lặng hoặc là loại thông báo kém quan trọng, thông báo bị đẩy vào `notification_queue`. Job `send_notification_digest` chạy định kỳ hàng ngày sẽ gom nhóm (Group By User) các thông báo này thành một bản tin duy nhất (Digest) để bắn 1 lần cho User, tránh làm phiền.

### 2026-09-08 — Phase 4: Khởi tạo Web SSR & Cấu trúc SEO

Khởi tạo thành công thư mục `web/` với nền tảng Angular 18 (bật sẵn tính năng Server-Side Rendering) để giải quyết triệt để bài toán SEO từ Google và mạng xã hội.

**Các mốc quan trọng đã đạt:**
- Cài đặt TailwindCSS để xây dựng layout nhanh chóng.
- Xây dựng tĩnh (Wireframe layout) trang Game (`GameComponent`) bao hàm toàn bộ 4 câu hỏi trọng tâm mà Game thủ Việt Nam thường tìm kiếm: 
  - Giá mua rẻ nhất.
  - Cấu hình máy yếu chơi được không.
  - Lịch sử ra mắt & Điểm đánh giá.
  - Game tương tự.
- Gắn Dynamic Meta Tags bằng `Meta` service của Angular để thay đổi `<title>` và `<meta name="description">` tự động khi chuyển route.
- Mở một endpoint mới ở Backend Python FastAPI (`/api/v1/og-image`) dùng thư viện Pillow để vẽ động thẻ ảnh OpenGraph (Chứa Logo, Tên Game và Giá Giảm Mới Nhất), cung cấp URL ảnh cho các thẻ chia sẻ lên Facebook/Zalo.

### 2026-09-08 — Phase 4: Deals, Free Games & Analytics

Hoàn tất 100% các hạng mục của Phase 4 với các bổ sung:
### 2026-09-08 — Phase 5: Khởi tạo Mobile App (Flutter)

Bắt đầu chiến dịch Mobile App để đẩy mạnh tương tác (Retention) thông qua Push Notification.
- Khởi tạo thành công project Flutter.
- Áp dụng cấu trúc `go_router` với `ShellRoute` để tạo Bottom Navigation Bar vững chắc.
- Tích hợp sẵn `flutter_riverpod` và `dio`.
- Dựng xong khung hiển thị tĩnh (Placeholder UI) cho 4 tab chính: Khám phá, Tìm kiếm, Thư viện, Cài đặt và đặc biệt là màn hình Game Detail độc lập.
- Nền tảng đã sẵn sàng để đón Client API sinh từ FastAPI OpenAPI.

### 2026-09-08 — Phase 5 (Phần 3): Widget & Privacy Policy (Hoàn tất Mobile App)

Chốt hạ Phase 5 với các yêu cầu khắt khe nhất để tăng trưởng và qua cửa duyệt Store:
- **Widget (Android)**: Cài đặt package `home_widget`, cấu trúc xong mã Native (XML Layout, XML Widget Info và `GameNewsWidgetProvider.java` class). App đã sẵn sàng bơm data (Elden Ring Sale 30%) từ Flutter ra ngoài màn hình chính của Android.
- **Privacy Policy**: Đã soạn thảo xong file `docs/PRIVACY_POLICY.md` (Song ngữ Việt/Anh). Văn bản giải trình cực kỳ chi tiết việc: "Chỉ lấy thông tin từ Public API của Steam thông qua định danh Steam ID 64, KHÔNG thu thập mật khẩu, KHÔNG bán dữ liệu". Sẵn sàng nộp lên Apple/Google Store.

**=> HOÀN TẤT CHECKPOINT PHASE 5.** Toàn bộ luồng từ lúc tải app -> đăng nhập -> xem deal -> nhận push báo giá -> ra xem widget ngoài màn hình đều đã thông suốt. Sẵn sàng tiến tới Phase 6 (Tin tức & Dịch).

### 2026-09-08 — Phase 6 (Phần 1): Crawler, Simhash & 3-Tier Entity Matching

Khởi động lõi thu thập tin tức của GameNews. Module này phải giải quyết lượng rác khổng lồ từ các trang tin trước khi tốn tiền gọi LLM API.
- **Quản lý Nguồn (Sources)**: Xây dựng CRUD API cho collection `sources` trong Mongo, quản lý URL RSS, trạng thái và độ tin cậy. Dùng thư viện `feedparser`.
- **Khử trùng lặp (Simhash)**: Đo khoảng cách Hamming giữa 2 bài viết (lọc tag HTML) để nhóm các bài trùng lặp lại (VD: cùng 1 deal). Tránh spam Feed của người dùng.
- **Bộ lọc Entity Matching 3 Tầng**:
  1. **Exact Match**: Bóc tách nội dung HTML tìm URL `store.steampowered.com/app/...` hoặc Epic Slug để tra ID chuẩn xác 100%.
  2. **Fuzzy Match**: So sánh độ tương đồng chuỗi (`SequenceMatcher`) của tiêu đề bài báo với danh sách `aliases_normalized` (ngưỡng >= 0.85).
  3. **Embedding Match (Qdrant)**: Chuẩn bị giao diện để gọi Embedding từ LLM nếu Tầng 1 và 2 thất bại. Bài nào rớt cả 3 Tầng sẽ bị đẩy vào **Hàng đợi duyệt tay (Manual Review)**.
- Khai báo thêm phụ thuộc `simhash`, `beautifulsoup4`, `feedparser` qua `uv`.
- Nâng cấp `qdrant` thành Required Dependency (503 nếu rớt) trong Healthcheck.
- **Nghiệm thu**: Chạy Script test với feed IGN, kéo thành công 20 bài, lọc simhash và log tỷ lệ khớp hoàn hảo. Đã fix lỗi Unicode (`cp1252`) trên PowerShell Windows trong lúc test.
