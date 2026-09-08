# PLAN.md — Kế hoạch phát triển

> Tên dự án: **gamesnews** — repo <https://github.com/zerosoul90/gamesnews>.

## 1. Định vị

Nền tảng tổng hợp thông tin game đa ngôn ngữ, ưu tiên thị trường Việt Nam,
gồm web + Android + iOS.

Bốn hướng sản phẩm (database, aggregator, cộng đồng, biên tập) là **chuỗi phụ
thuộc**, không làm song song:

```
Database game  →  Tổng hợp nội dung  →  Cộng đồng  →  Biên tập
   (nền)           (traffic + SEO)      (giữ chân)    (khác biệt)
```

**Mũi nhọn giai đoạn đầu (đã chốt):** giá VND kèm cảnh báo đáy lịch sử.
Giftcode / lịch banner game mobile lùi xuống Phase 8, không làm song song.

## 2. Ràng buộc

- **Toàn bộ nguồn dữ liệu và hạ tầng phải miễn phí.** Xem `DATA-SOURCES.md`.
- Ba khoản không thể bằng 0: Apple Developer 99 USD/năm, Google Play Console
  25 USD một lần, domain (~250k/năm). Server dùng Oracle Cloud Always Free.
- Không tái bản nguyên văn nội dung có bản quyền. Chỉ tiêu đề + tóm tắt tự
  viết + link nguồn.

## 3. Stack

| Lớp | Lựa chọn | Ghi chú |
|---|---|---|
| Backend | Python 3.12 + FastAPI | async xuyên suốt |
| DB chính | MongoDB | time-series collection cho metrics |
| Search | Meilisearch | tên game, tiếng Việt không dấu |
| Vector | Qdrant | "game giống X", bài liên quan |
| Cache / queue | Redis | |
| Scheduler | Arq | chạy trên Redis sẵn có; dùng chung cho giá + metrics |
| Web | Angular (TypeScript) + `@angular/ssr` | quen tay; SSR bắt buộc vì SEO là kênh chính |
| Mobile | Flutter (Dart) + Riverpod | một codebase cho Android + iOS |
| Push | Firebase Cloud Messaging | miễn phí không giới hạn |
| Analytics | Umami self-host | |
| Hạ tầng | Docker Compose trên Oracle Cloud Always Free | 4 core ARM / 24GB |

## 4. Quyết định còn mở

1. **Có làm affiliate không** — ảnh hưởng tới việc dùng Reddit/RAWG API
   (tầng miễn phí của họ chỉ cho phi thương mại).

**Ngôn ngữ nội dung MVP (đã chốt):** Việt + Anh. Route i18n và `hreflang` phải
dựng ngay từ Phase 4 để thêm ngôn ngữ sau không phải đổi cấu trúc URL.

## 5. Lộ trình

Mỗi phase kết thúc bằng một checkpoint kiểm chứng được. Không sang phase sau
khi checkpoint chưa đạt.

> **Lưu ý thứ tự:** module tin tức bị đẩy xuống sau module giá. Lý do: giá là
> mũi nhọn đã chọn, tự sinh từ dữ liệu, không có rủi ro bản quyền; còn tin tức
> là phần đắt nhất về vận hành và rủi ro nhất về pháp lý.

### Phase 0 — Nền móng · 1–2 tuần

- Repo, cấu trúc thư mục, `docker-compose.yml` đủ MongoDB + Meilisearch +
  Qdrant + Redis + FastAPI + worker Arq
- Skeleton FastAPI: health check, config, logging, migration
- CI cơ bản (lint + test)
- `CLAUDE.md`, `PROGRESS.md`

**Checkpoint:** `docker compose up` khởi động toàn bộ stack, `/health` trả về
trạng thái xanh của cả 4 dịch vụ phụ thuộc.

### Phase 1 — Catalog + Search · 3–4 tuần

- Đồng bộ Steam (`IStoreService/GetAppList` + `appdetails`) — thay IGDB từ
  2026-09-08, xem `DATA-SOURCES.md`
- Entity `game` với alias đa ngôn ngữ + bảng ID mapping
  (Steam AppID / Google Play / App Store / Epic slug / CheapShark)
- Bổ sung game mobile từ Google Play + App Store (thư viện scraper open source)
- Index Meilisearch, cấu hình normalize tiếng Việt
- API tìm kiếm + facet (nền tảng, thể loại, năm)
- Trang admin xem/sửa entity

**Checkpoint:** các truy vấn `elden ring`, `elden`, `erden ring`, `vong elden`
đều trả về đúng game ở vị trí đầu. Catalog ≥ 50.000 game.

### Phase 2 — Giá & Deal · 3–4 tuần

- Adapter: Steam `appdetails` (cc=vn), Epic GraphQL + freeGamesPromotions,
  GOG, CheapShark
- Scheduler phân tầng (hot 1–4h / ấm 24h / lạnh 7 ngày)
- `price_current` (upsert) + `price_history` (append khi đổi giá)
- Tính `lowest_ever`, `lowest_ever_date`, cờ đang ở đáy
- API: giá theo game, danh sách deal, game free tuần này
- Cảnh báo game bị khoá khu vực VN

**Checkpoint:** theo dõi ổn định 5.000 game hot; biểu đồ giá 30 ngày khớp với
SteamDB khi đối chiếu thủ công 20 game mẫu; không có dòng history trùng lặp.

### Phase 3 — Người dùng & Thông báo · 3–4 tuần

- Auth + Steam OpenID
- Import thư viện (`IPlayerService/GetOwnedGames`) và wishlist
  (`IWishlistService/GetWishlist`), kèm hướng dẫn có ảnh để đặt profile public
- Epic: màn hình tick nhanh game free theo tuần
- Follow game / series / studio / nền tảng
- Ngưỡng cảnh báo linh hoạt (dưới X đồng / giảm ≥ Y% / chạm đáy lịch sử)
- FCM push: gộp digest cho tin không gấp, đẩy tức thì cho 3 loại ưu tiên,
  giờ im lặng, bật/tắt từng loại

**Checkpoint:** người dùng nhận push đúng trong 15 phút kể từ khi giá chạm
ngưỡng; **không bao giờ** nhận thông báo giảm giá cho game đã sở hữu.

### Phase 4 — Web công khai & SEO · 3–4 tuần

- SSR, trang game trả lời sẵn: chơi được máy yếu không / giá bao nhiêu /
  ra ngày nào / mua ở đâu
- Trang deal, trang free tuần này
- Thẻ chia sẻ dạng ảnh sinh phía server (Pillow hoặc Satori)
- Sitemap, structured data, i18n route
- Web dùng được đầy đủ mà **không** bắt cài app

**Checkpoint:** Lighthouse SEO ≥ 90; tắt JavaScript vẫn đọc được đủ nội dung
trang game; thẻ chia sẻ render đúng trên Facebook và Zalo.

### Phase 5 — Mobile · 4–6 tuần

- Flutter, dùng lại toàn bộ API
- Deep link từ web sang app
- Widget Android + Live Activity iOS cho đếm ngược và deal
- Đăng ký Apple Developer + Google Play Console

**Checkpoint:** build lên TestFlight và Internal Testing, chạy được trên máy
thật, nhận push đúng.

### Phase 6 — Tin tức & dịch · 3–4 tuần

- 10–15 nguồn RSS (Việt + Anh)
- Khử trùng lặp simhash
- Gắn entity 3 tầng: exact (link store trong bài) → fuzzy theo alias →
  embedding; dưới ngưỡng thì đẩy vào hàng đợi duyệt
- Vòng phản hồi: mỗi lần duyệt tay sinh alias mới
- Tóm tắt + dịch qua LLM adapter (Gemini/Groq free tier, hoặc model nhỏ
  self-host qua llama.cpp). Chỉ dịch tiêu đề + 2–3 câu, không dịch nguyên bài

**Checkpoint:** tỉ lệ gắn entity tự động ≥ 85%; tin quốc tế lên feed tiếng Việt
trong vòng 2 giờ; không có bài nào hiển thị quá 3 câu từ nguồn gốc.

### Phase 7 — Chỉ số hot & Streamer · 3–4 tuần

- CCU Steam (`GetNumberOfCurrentPlayers`), most-played, top sellers theo cc=vn
- Twitch: Get Streams theo game, EventSub `stream.online`/`stream.offline`
- YouTube: WebSub trên feed kênh (không tốn quota Data API)
- Chỉ số hot chuẩn hoá theo percentile 30 ngày; hai bảng riêng
  "Phổ biến nhất" và "Đang tăng mạnh"
- Rollup time-series: raw 15 phút giữ 7 ngày → giờ giữ 90 ngày → ngày giữ mãi
- Danh sách streamer Việt (curate tay ban đầu)

**Checkpoint:** bảng "Đang tăng mạnh" không bị CS2/Dota 2 chiếm chỗ; push
"streamer đang follow lên sóng" đến trong 60 giây.

### Phase 8 — Cộng đồng & Giftcode

- Đánh giá + điểm người dùng (ẩn cho tới khi ≥ 20 lượt), chống review bombing
- Giftcode + lịch banner game mobile
- Mở hàng đợi duyệt entity cho cộng đồng, badge ghi công
- Thống kê thư viện cá nhân + bản tổng kết cuối năm

## 6. Nguyên tắc xuyên suốt

1. **Provider pattern cho mọi nguồn.** Tầng miễn phí có thể biến mất bất cứ
   lúc nào. Mỗi nguồn dữ liệu và mỗi LLM nằm sau một interface chung.
2. **Không phase nào được bỏ checkpoint.**
3. **Điểm chết duy nhất phải được nhận diện.** Steam `appdetails` là endpoint
   không chính thức — luôn có đường lùi.
4. **Không lưu dữ liệu người dùng quá mức cần.** Thư viện Steam chỉ lưu appid
   + playtime + mốc đồng bộ, có nút xoá.
