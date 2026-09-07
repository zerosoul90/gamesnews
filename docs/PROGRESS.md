# PROGRESS.md — Tiến độ

**Phase hiện tại:** Phase 0 — Nền móng
**Cập nhật lần cuối:** chưa bắt đầu

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

**Checkpoint:** `docker compose up` khởi động toàn bộ stack, `/health` xanh cả
4 dịch vụ phụ thuộc.

- [ ] Khởi tạo repo, cấu trúc thư mục theo `CLAUDE.md`
- [ ] `docker-compose.yml`: MongoDB, Meilisearch, Qdrant, Redis, app
- [ ] Skeleton FastAPI: config, logging, health check
- [ ] `adapters/base.py` — interface chung cho mọi nguồn
- [ ] CI: ruff + mypy + pytest
- [ ] Đăng ký key: Twitch developer (IGDB), Steam Web API

---

## Phase 1 — Catalog + Search

**Checkpoint:** `elden ring` / `elden` / `erden ring` / `vong elden` đều ra
đúng game ở vị trí đầu. Catalog ≥ 50.000 game.

- [ ] Adapter IGDB + job đồng bộ ban đầu
- [ ] Collection `games` theo `SCHEMA.md`, index đầy đủ
- [ ] Sinh `aliases_normalized` (bỏ dấu, lowercase, chuẩn hoá khoảng trắng)
- [ ] Bảng ID mapping: IGDB / Steam AppID / Epic slug / CheapShark
- [ ] Bổ sung game mobile từ Google Play + App Store
- [ ] Index Meilisearch + cấu hình tiếng Việt
- [ ] API tìm kiếm + facet
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
