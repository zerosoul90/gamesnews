# PROGRESS.md — Tiến độ

**Phase hiện tại:** Phase 1 — Catalog + Search
**Cập nhật lần cuối:** 2026-09-07

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

- [ ] Adapter IGDB + job đồng bộ ban đầu — **chặn**: chưa có key Twitch
- [x] Collection `games` theo `SCHEMA.md`, index đầy đủ
- [x] Sinh `aliases_normalized` (bỏ dấu, lowercase, chuẩn hoá khoảng trắng)
- [x] Bảng ID mapping + `find_game_by_external_id` — **khung** đã xong; dữ liệu
      thật phải chờ adapter
- [ ] Bổ sung game mobile từ Google Play + App Store
- [x] Index Meilisearch + cấu hình tiếng Việt
- [x] API tìm kiếm + facet
- [ ] Trang admin xem/sửa entity

---

## Phase 2 — Giá & Deal

**Checkpoint:** theo dõi ổn định 5.000 game hot; biểu đồ giá 30 ngày khớp khi
đối chiếu tay 20 game mẫu; không có dòng history trùng.

- [ ] Adapter Steam appdetails (cc=vn) + token bucket tôn trọng 200 req/5 phút
- [ ] Adapter Epic (GraphQL + freeGamesPromotions)
- [ ] Adapter GOG, CheapShark
- [ ] Scheduler phân tầng hot / ấm / lạnh
- [ ] `price_current` + `price_history` (chỉ ghi khi giá đổi)
- [ ] Tính `lowest_ever`, cờ đang ở đáy
- [ ] Cờ khoá khu vực VN
- [ ] API: giá theo game, danh sách deal, free tuần này

---

## Phase 3 — Người dùng & Thông báo

**Checkpoint:** push đến trong 15 phút khi giá chạm ngưỡng; không bao giờ báo
giảm giá game đã sở hữu.

- [ ] Auth + Steam OpenID
- [ ] Import `GetOwnedGames` + `GetWishlist` (tra ngược tên từ appid)
- [ ] Hướng dẫn có ảnh để đặt profile Public + tự kiểm tra lại
- [ ] Màn hình tick nhanh game free Epic theo tuần
- [ ] Follow game / series / studio / nền tảng
- [ ] Ngưỡng cảnh báo linh hoạt
- [ ] FCM: digest, giờ im lặng, bật/tắt từng loại

---

## Phase 4 — Web công khai & SEO

**Checkpoint:** Lighthouse SEO ≥ 90; tắt JS vẫn đọc đủ nội dung; thẻ chia sẻ
render đúng trên Facebook và Zalo.

- [ ] Chốt framework, dựng SSR
- [ ] Trang game trả lời sẵn 4 câu hỏi dài tiếng Việt
- [ ] Trang deal, trang free tuần này
- [ ] Thẻ chia sẻ dạng ảnh sinh phía server
- [ ] Sitemap, structured data, i18n route
- [ ] Umami self-host

---

## Phase 5 — Mobile

- [ ] Flutter app, dùng lại API
- [ ] Deep link, push
- [ ] Widget Android / Live Activity iOS
- [ ] Apple Developer + Google Play Console

---

## Phase 6 — Tin tức & dịch

**Checkpoint:** gắn entity tự động ≥ 85%; tin quốc tế lên feed tiếng Việt
trong 2 giờ.

- [ ] Quản lý nguồn + 10–15 RSS
- [ ] Khử trùng lặp simhash
- [ ] Gắn entity 3 tầng + hàng đợi duyệt
- [ ] Vòng phản hồi sinh alias từ mỗi lần duyệt tay
- [ ] LLM adapter tóm tắt + dịch

---

## Phase 7 — Chỉ số hot & Streamer

**Checkpoint:** bảng "Đang tăng mạnh" không bị game top thường trực chiếm chỗ;
push streamer live trong 60 giây.

- [ ] Thu thập CCU, most played, top sellers cc=vn, reviews
- [ ] Twitch Get Streams + EventSub
- [ ] YouTube WebSub + job gia hạn subscription
- [ ] Chuẩn hoá percentile, hai bảng hot/rising
- [ ] Rollup time-series
- [ ] Danh sách streamer Việt (curate tay)

---

## Phase 8 — Cộng đồng & Giftcode

- [ ] Đánh giá + điểm người dùng (ẩn dưới 20 lượt), chống review bombing
- [ ] Giftcode + lịch banner mobile
- [ ] Mở hàng đợi duyệt cho cộng đồng, badge
- [ ] Thống kê thư viện + tổng kết cuối năm

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

---

## Đang chặn

**Key ngoài — việc của người dùng.** Đây là mục 7 còn nợ của Phase 0, và giờ nó
đang chặn thật:

| Biến | Đăng ký ở | Chặn cái gì |
|---|---|---|
| `TWITCH_CLIENT_ID` + `TWITCH_CLIENT_SECRET` | <https://dev.twitch.tv/console/apps> | Phase 1 mục 1 — adapter IGDB, và qua đó là checkpoint "catalog ≥ 50.000 game" |
| `STEAM_API_KEY` | <https://steamcommunity.com/dev/apikey> | Phase 2 (giá) và Phase 3 (thư viện người dùng) |

Cùng cặp key Twitch dùng luôn cho IGDB. Luồng client-credentials không dùng tới
OAuth Redirect URL, điền `http://localhost` là được.
