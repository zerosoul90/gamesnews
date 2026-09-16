# Mockup giao diện đầy đủ — bản giao việc

Tài liệu này đi kèm `docs/mockup/index.html` (mở thẳng bằng trình duyệt, không
cần server). Mục đích: mô tả **toàn bộ** giao diện dự kiến, và quan trọng hơn,
nói rõ màn nào dựng được ngay và màn nào còn thiếu backend.

Mọi con số và mọi tên trường trong đây đều **đọc từ hệ thống đang chạy ngày
2026-09-17**, không phải bịa. Chỗ nào chưa có thì ghi thẳng là chưa có.

## 0. Đọc trước khi viết dòng code nào

### Backend có 44 đường, web đang dùng 4

Đó là gốc của cảm giác "giao diện không đầy đủ". Không phải backend yếu — là
web chưa gọi tới.

### Nhóm endpoint người dùng CHỈ CÓ ĐƯỜNG GHI

Đây là cái bẫy lớn nhất của cả tài liệu này. Đừng bắt đầu dựng trang "Thư viện
của tôi" rồi mới phát hiện không có gì để đọc:

| Đường | Có | KHÔNG có |
|---|---|---|
| `/api/v1/user/library` | `DELETE`, `POST /library/sync` | **`GET`** |
| `/api/v1/user/alerts` | `POST` | **`GET`**, `DELETE` |
| `/api/v1/user/follows` | `POST` | **`GET`**, `DELETE` |
| `/community/reviews` | `POST` | **`GET`** (không đọc được đánh giá của một game) |

Bốn màn phụ thuộc chúng vì thế là **CẦN API MỚI**, không phải "dựng được ngay".

### Ràng buộc cứng, không được lách

Lấy từ `CLAUDE.md`. Vi phạm là vấn đề pháp lý, không phải lỗi giao diện.

1. **Không bao giờ render nguyên văn bài gốc.** `articles.original_content` giữ
   HTML đầy đủ của nguồn. API `/news` đã chặn hai lớp và **không trả trường đó**
   — đừng thêm đường nào để lấy nó ra. Thẻ tin chỉ được có: tiêu đề (đã dịch),
   tóm tắt tự viết, tên nguồn, và link ra bài gốc.
2. **Không hiện điểm tổng hợp Metacritic.** Điểm phê bình tự tính.
3. **Không bao giờ gửi/hiện cảnh báo giảm giá cho game người dùng đã sở hữu.**
   Ảnh hưởng trực tiếp tới màn Cảnh báo giá và Thư viện.
4. **Thư viện Steam chỉ lưu appid + playtime + mốc đồng bộ.** Không lịch sử mua.

### Hệ thiết kế đang dùng

Tailwind, nền tối. Bảng màu lấy từ code đang chạy — giữ nguyên để màn mới không
lạc khỏi màn cũ:

| Vai trò | Lớp |
|---|---|
| Nền trang | `bg-slate-900` |
| Thẻ / khối | `bg-slate-800`, viền `border-slate-700` |
| Viền khi hover | `hover:border-blue-500` |
| Chữ chính / phụ | `text-white` / `text-slate-400` |
| Giá tốt, trạng thái tốt | `text-green-400` |
| Huy hiệu giảm giá | `bg-red-600` |
| Đáy lịch sử | `bg-yellow-500 text-black` |
| Nút chính | `bg-blue-600 hover:bg-blue-500` |

Component dùng lại được: `app-nav` (`web/src/app/components/nav/`). Thêm mục mới
vào mảng `muc` trong `nav.component.ts`, đừng chép lại thanh nav.

### Ba trạng thái, màn nào cũng phải có

Bug hay gặp nhất của mấy màn hiện tại là quên hai cái sau:

- **đang tải** — và nếu là "xem thêm" thì phải giữ danh sách cũ trên màn hình,
  đừng thay cả trang bằng chữ "đang tải" (xem `dangTaiThem` trong
  `news.component.ts`).
- **rỗng** — nói rõ vì sao rỗng, đừng để trắng.
- **lỗi** — kèm nút thử lại.

---

## 1. Bảng toàn cảnh

Trạng thái: **XONG** = đã chạy trên production · **DỰNG ĐƯỢC NGAY** = API có
sẵn, chỉ thiếu giao diện · **CẦN API MỚI** = phải viết backend trước.

| # | Màn | Route | API | Trạng thái |
|---|---|---|---|---|
| 1 | Deal | `/deals` | `GET /deals` | XONG |
| 2 | Game miễn phí | `/free` | `GET /free-games` | XONG |
| 3 | Tin tức | `/news` | `GET /news` | XONG |
| 4 | Chi tiết game | `/game/:slug` | `GET /games/by-slug/{slug}` | XONG (thiếu 3 khối, xem §2.4) |
| 5 | Kết quả tìm kiếm | `/search` | `GET /search` | DỰNG ĐƯỢC NGAY |
| 6 | Ô tìm kiếm trên nav | (nav) | `GET /search` | DỰNG ĐƯỢC NGAY |
| 7 | Trang chủ thật | `/` | nhiều | DỰNG ĐƯỢC NGAY |
| 8 | Thống kê | `/thong-ke` | `GET /dashboard/stats` | DỰNG ĐƯỢC NGAY |
| 9 | Wrapped | `/wrapped/:year` | `GET /api/v1/user/me/wrapped/{year}` | DỰNG ĐƯỢC NGAY |
| 10 | Huy hiệu người dùng | `/nguoi-dung/:id` | `GET /community/users/{id}/badges` | DỰNG ĐƯỢC NGAY |
| 11 | Đăng nhập Steam | (nút trên nav) | `GET /api/v1/auth/steam/login` | DỰNG ĐƯỢC NGAY |
| 12 | Thư viện của tôi | `/thu-vien` | — | **CẦN API MỚI** |
| 13 | Cảnh báo giá | `/canh-bao` | — | **CẦN API MỚI** |
| 14 | Đang theo dõi | `/theo-doi` | — | **CẦN API MỚI** |
| 15 | Đánh giá của một game | (trong §2.4) | — | **CẦN API MỚI** |

---

## 2. Từng màn

### 2.4 Chi tiết game — ba khối còn thiếu

Màn này đã khá đầy đủ (tên, ảnh, thể loại, nhà phát triển, điểm Steam, giá thấp
nhất, bảng so giá, biểu đồ 30 ngày, cấu hình máy). Ba khối cần thêm:

**a) Giá quốc tế nhiều store — DỰNG ĐƯỢC NGAY, wiring đã có.**
`GET /games/by-slug/{slug}` đã trả `intl_prices`, và
`game.component.html` đã có `*ngIf="g.intl_prices as intl"`. Hiện phần lớn game
trả `null` vì vòng xoay CheapShark mới quét được một phần kho — **không phải
lỗi**, dữ liệu đang đầy dần. Giá là **USD dạng cent**, đừng trộn vào bảng VND.

**b) Tin liên quan — DỰNG ĐƯỢC NGAY.**
`GET /news?game_id={game_id}` đã nhận tham số lọc. Chỉ ~1/7 bài gắn được game
nên khối này thường rỗng; rỗng thì ẩn hẳn.

**c) Đánh giá cộng đồng — MỘT NỬA.**
`GET /community/games/{game_id}/reviews/score` đọc được điểm tổng. Nhưng
**không có `GET` để lấy danh sách đánh giá** — chỉ `POST /community/reviews` để
gửi. Nên hiện được điểm, không hiện được nội dung.

### 2.5–2.6 Tìm kiếm

`GET /search?q=&limit=&page=`. Hình dạng thật:

```json
{
  "query": "elden", "total": 51, "page": 1, "per_page": 20,
  "hits": [{
    "id": "...", "slug": "elden-ring",
    "titles": { "primary": "Elden Ring", "vi": null, "ja": "エルデンリング" },
    "platforms": ["pc", "ps5"], "genres": ["action-rpg"],
    "type": "game", "release_year": 2022, "cover": null
  }]
}
```

Hai điều dễ sai:

- `titles.vi` **thường là `null`**. Hiện `titles.vi || titles.primary`.
- `cover` **có thể `null`** ngay cả với game lớn (Elden Ring đang là `null`).
  Phải có ô giữ chỗ, đừng để ảnh vỡ — đúng lỗi trang `/free` cũ mắc phải.

Ô tìm kiếm đặt trên `app-nav`, gõ xong nhảy sang `/search?q=`. Nhớ debounce nếu
làm gợi ý tức thời.

### 2.7 Trang chủ thật

Hiện `/` đang 302 sang `/deals`. Trang chủ nên gom: 3–4 deal đáy lịch sử, game
miễn phí tuần này, 5 tin mới nhất, ô tìm kiếm lớn. Tất cả đều từ API đã có.

### 2.8 Thống kê

`GET /dashboard/stats` trả đúng bốn số:

```json
{"total_games_tracked": 28662, "total_deals_now": 2217,
 "total_free_games": 1, "total_historical_lows": 1770}
```

Bốn thẻ số lớn. Đừng thêm biểu đồ — không có dữ liệu chuỗi thời gian nào ở
endpoint này.

### 2.12–2.14 Các màn cần API mới

Giao diện thiết kế được ngay, nhưng **phải chờ backend**. Đề xuất hình dạng
(cần chốt với chủ dự án trước khi hiện thực):

```
GET /api/v1/user/library?limit=&offset=
    -> { items: [{ game: {slug,title,cover}, playtime_minutes, synced_at }],
         total }

GET /api/v1/user/alerts
    -> [{ id, game: {...}, condition_type, value, triggered_at, created_at }]
DELETE /api/v1/user/alerts/{id}

GET /api/v1/user/follows
    -> [{ id, target_type, target: {...}, created_at }]
DELETE /api/v1/user/follows/{id}

GET /community/games/{game_id}/reviews?limit=&offset=
    -> { reviews: [{ id, user:{id,name}, score, body, created_at }], total }
```

**Ràng buộc số 3 áp vào đây:** màn Cảnh báo giá không được hiện cảnh báo cho
game người dùng đã sở hữu. Việc lọc nên làm ở **backend**, đừng để giao diện tự
lọc — giao diện quên một lần là vi phạm.

---

## 3. Thứ tự đề nghị

Xếp theo giá trị chia cho công sức, không phải theo số thứ tự bảng trên.

1. **Ô tìm kiếm + trang kết quả** (#5, #6) — API sẵn, và tìm kiếm là thứ người
   dùng mong đợi nhất ở một trang 28.662 game.
2. **Ba khối của trang game** (#4a, #4b) — wiring đã có, chỉ cần render.
3. **Trang chủ thật** (#7) — gom từ API sẵn, bỏ cái 302.
4. **Đăng nhập Steam + trạng thái trên nav** (#11) — mở đường cho mọi màn cá
   nhân hoá phía sau.
5. **Thống kê** (#8) — rẻ, và là bằng chứng sống cho thấy hệ thống có dữ liệu.
6. **Nhóm cần API mới** (#12–#15) — chốt hình dạng API trước, rồi làm cả cụm.

## 4. Đừng lặp lại bốn lỗi đã sửa

Bốn cái này đều đã thật sự xảy ra trong repo, không phải cảnh báo lý thuyết:

1. **Trang tĩnh giả làm trang thật.** `/free` từng là HTML ghi cứng với ảnh CDN
   đã chết và giá bịa. Trang nói sai còn tệ hơn trang trống.
2. **Sắp xếp cố định + cắt ngọn.** Job giá CheapShark từng luôn lấy 200 bản ghi
   `_id` nhỏ nhất, nên 83% kho không bao giờ được cập nhật. Danh sách phân trang
   nào cũng phải có khoá xoay vòng đổi sau khi phục vụ.
3. **Số tổng xanh không nói gì về từng phần.** Luôn đếm theo từng nguồn / từng
   nhóm khi nghiệm thu.
4. **Ảnh `null` không phải trường hợp hiếm.** `cover` và `cover_image_url` null
   rất thường. Mọi chỗ hiện ảnh phải có nhánh vắng mặt.
