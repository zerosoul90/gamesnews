# PHASE 1 — Catalog + Search

## Trước khi bắt đầu

Đọc `CLAUDE.md`, `PLAN.md`, `DATA-SOURCES.md`, `SCHEMA.md`, `PROGRESS.md`.
Xác nhận Phase 0 đã đạt checkpoint.

## Mục tiêu

Có một catalog game chuẩn hoá và tìm kiếm được bằng tiếng Việt.

Đây là phase quan trọng nhất của toàn dự án. Entity game sai ở đây thì mọi
phase sau đều hỏng, và rất khó sửa về sau. Ưu tiên làm đúng hơn làm nhanh.

## Phạm vi

**LÀM:** đồng bộ IGDB, entity `games`, alias, ID mapping, catalog mobile,
Meilisearch, API tìm kiếm, admin xem/sửa entity.

**KHÔNG LÀM:** giá, tin tức, chỉ số hot, người dùng, Qdrant. Qdrant đã chạy
trong compose nhưng chưa dùng ở phase này.

## Việc cần làm, theo thứ tự

### 1. Adapter IGDB

Qua tài khoản Twitch developer. Tôn trọng ~4 req/s. Xử lý phân trang cho toàn
bộ catalog. Lấy: tên, alternative names, slug, platform, genre, developer,
publisher, release date theo region, cover, screenshot, external id (đặc biệt
là Steam AppID).

### 2. Collection `games`

Đúng theo `SCHEMA.md`. Index bắt buộc: `external_ids.steam_appid`,
`external_ids.igdb`, `slug`, `aliases_normalized`.

Chú ý ba chỗ dễ làm sai:

- `release_dates` là mảng theo region + platform, **không** phải một trường duy nhất
- `type` phân biệt game / dlc / demo / bundle; DLC phải trỏ `parent_game`
- `is_live_service` cho game gacha/MMO — nhóm này không có "một ngày ra mắt"

### 3. Chuẩn hoá alias

Hàm `normalize_vi(text)`: lowercase, bỏ dấu tiếng Việt, chuẩn hoá khoảng trắng
liên tiếp thành một, bỏ ký tự đặc biệt. Sinh `aliases_normalized` từ `aliases`.

Nguồn alias ban đầu: tên chính, alternative names của IGDB, tên không dấu, tên
viết liền (bỏ hết khoảng trắng), tên tiếng Nhật/Trung nếu có.

Viết test cho hàm này trước khi dùng. Ít nhất 20 case, gồm tên có dấu, tên
Nhật, tên có ký tự La Mã (II, III), tên có dấu hai chấm.

### 4. Bảng ID mapping

Trong `external_ids`. Steam AppID là khoá cầu nối chính. Viết sẵn hàm tra ngược
`find_game_by_external_id(source, id)` — mọi phase sau đều dùng.

### 5. Catalog mobile

Bổ sung game mobile từ Google Play và App Store bằng thư viện scraper open
source. IGDB phủ mảng này rất kém mà đây lại là mảng quan trọng nhất với thị
trường VN.

Chạy tách job, có thể lỗi mà không làm hỏng job IGDB.

### 6. Meilisearch

Index `games` với searchable attributes theo thứ tự ưu tiên: `titles.primary`,
`titles.vi`, `aliases_normalized`, `aliases`.
Filterable: platform, genre, release year, type.
Bật typo tolerance. Cấu hình ranking rules để game chính xếp trên DLC.

Job reindex chạy lại được, và job đồng bộ delta khi entity đổi.

### 7. API tìm kiếm

`GET /search` với query, facet filter, phân trang. Trả về cả facet count.

### 8. Admin entity

Trang tối giản: tìm entity, xem chi tiết, sửa alias, gộp hai entity trùng.
Chức năng gộp phải cập nhật cả `external_ids` và `aliases`.

## DỪNG LẠI ĐỂ REVIEW

Sau mục 2 (schema thực tế sau khi đã thấy dữ liệu IGDB thật) và sau mục 6
(cấu hình Meilisearch). Đây là hai chỗ khó sửa nhất về sau.

## Checkpoint nghiệm thu

- [ ] Catalog ≥ 50.000 game
- [ ] `elden ring`, `elden`, `erden ring`, `vong elden` đều ra Elden Ring ở vị
      trí đầu
- [ ] `エルデンリング` cũng ra đúng game
- [ ] Tìm một game mobile phổ biến ở VN (ví dụ Liên Quân) ra đúng kết quả
- [ ] Lọc theo platform + năm cho ra facet count đúng
- [ ] Chạy lại job đồng bộ không sinh entity trùng
- [ ] Test `normalize_vi` xanh toàn bộ

## Sau khi xong

Cập nhật `PROGRESS.md`. Ghi lại tỉ lệ game có Steam AppID — con số này quyết
định độ phủ của Phase 2.
