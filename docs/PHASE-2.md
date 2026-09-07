# PHASE 2 — Giá & Deal

## Trước khi bắt đầu

Đọc `CLAUDE.md`, `PLAN.md`, `DATA-SOURCES.md`, `SCHEMA.md`, `PROGRESS.md`.
Xác nhận Phase 1 đã đạt checkpoint.

Đây là mũi nhọn đã chốt của sản phẩm. Làm cho đúng và bền, đừng làm nhanh.

## Phạm vi

**LÀM:** adapter Steam/Epic/GOG/CheapShark, scheduler phân tầng, price_current,
price_history, đáy lịch sử, API deal, cờ khoá khu vực VN.

**KHÔNG LÀM:** thông báo cho người dùng (Phase 3), giao diện web (Phase 4).
API trả JSON là đủ.

## Ràng buộc quyết định toàn bộ thiết kế

Steam `appdetails` giới hạn **~200 request mỗi 5 phút trên mỗi IP**, và mỗi
request chỉ nhận **một appid với một mã quốc gia**. Tức khoảng 57.000
request/ngày. Không đủ để quét toàn catalog. Mọi thiết kế phải xuất phát từ
con số này.

Đây cũng là endpoint **không chính thức** — Valve có thể đổi bất cứ lúc nào.
Phải có đường lùi, không được để nó thành điểm chết duy nhất.

## Việc cần làm, theo thứ tự

### 1. Adapter Steam giá

`store.steampowered.com/api/appdetails?appids={id}&cc=vn&filters=price_overview`

Dùng chung token bucket từ `adapters/base.py`. Bucket này phải dùng chung với
mọi job Steam khác (kể cả CCU ở Phase 7) vì giới hạn tính theo IP.

Xử lý: game free, game chưa ra mắt, game bị gỡ, game không bán ở VN
(response thiếu `price_overview` → đánh dấu `region_locked_vn`).

### 2. Adapter Epic

- `store-site-backend-static-ipv4.ak.epicgames.com/freeGamesPromotions` cho
  game miễn phí hàng tuần — ổn định, ưu tiên
- `www.epicgames.com/graphql` → `Catalog.searchStore` cho giá và
  `promotions` / `upcomingPromotionalOffers` — có bot protection, phải chịu
  được 403 mà không làm hỏng job

### 3. Adapter GOG và CheapShark

CheapShark làm nguồn đối chiếu, phát hiện sai lệch. Không cần key.

### 4. Scheduler phân tầng

Ba tầng:

| Tầng | Điều kiện | Chu kỳ |
|---|---|---|
| Hot | có trong wishlist người dùng, hoặc top phổ biến | 1–4 giờ |
| Ấm | game có lượt xem trong 30 ngày | 24 giờ |
| Lạnh | phần còn lại | 7 ngày |

Tầng được tính lại định kỳ, không cố định. Ngoài ra: tăng tần suất trong các
đợt sale lớn của Steam (Summer/Autumn/Winter/Spring, Next Fest).

Scheduler phải tự điều tiết theo quota còn lại, không được để cạn bucket rồi
job khác chết đói.

Job chạy trên worker Arq, khác tiến trình với API. Vì vậy **token bucket phải
nằm trong Redis**, không phải trong bộ nhớ tiến trình — nếu không, mỗi worker
sẽ có bucket riêng và tổng số request vượt quota Steam.

### 5. Lưu giá

Theo `SCHEMA.md`. Hai điểm bắt buộc:

- `price_current` **upsert** theo `(game_id, store, region)`
- `price_history` **chỉ append khi giá thực sự đổi**. Poll mà giá không đổi thì
  không ghi gì. Đây là điều kiện sống còn về dung lượng.

### 6. Đáy lịch sử

Tính `lowest_ever`, `lowest_ever_date`, `is_historical_low` mỗi khi giá đổi.
Đây là con số người mua quan tâm hơn cả % giảm.

### 7. API

- `GET /games/{id}/prices` — giá hiện tại mọi store, mọi region đang theo dõi
- `GET /games/{id}/price-history?days=30` — dữ liệu vẽ biểu đồ
- `GET /deals` — sắp xếp theo **chất lượng deal**, không theo % giảm thuần
  (giảm 90% từ giá gốc thổi phồng là vô nghĩa; cân nhắc khoảng cách tới đáy
  lịch sử)
- `GET /free-games` — free tuần này, gom mọi store

## DỪNG LẠI ĐỂ REVIEW

Sau mục 4 (thiết kế scheduler và phân bổ quota) — trình bày phép tính quota cụ
thể trước khi code. Và sau mục 6.

## Checkpoint nghiệm thu

- [ ] Theo dõi ổn định 5.000 game hot suốt 48 giờ không cạn quota, không bị chặn
- [ ] Đối chiếu tay 20 game mẫu: giá VND và % giảm khớp với trang Steam
- [ ] Biểu đồ giá 30 ngày khớp khi so với dữ liệu công khai
- [ ] `price_history` không có hai dòng liên tiếp cùng giá
- [ ] Game không bán ở VN được đánh dấu đúng, không sinh dòng giá rác
- [ ] Tắt mạng giữa chừng → job retry và phục hồi, không mất dữ liệu

## Sau khi xong

Cập nhật `PROGRESS.md`. Ghi lại mức tiêu thụ quota thực tế mỗi ngày — con số
này quyết định được bao nhiêu game ở tầng hot.
