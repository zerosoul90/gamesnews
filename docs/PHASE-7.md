# PHASE 7 — Chỉ số hot & Streamer

## Trước khi bắt đầu

Đọc `CLAUDE.md`, `PLAN.md`, `DATA-SOURCES.md`, `SCHEMA.md`, `PROGRESS.md`.
Xác nhận Phase 6 đã đạt checkpoint.

## Lưu ý về thị trường VN

Twitch bị các nhà mạng Việt Nam chặn on-off nhiều năm. Hệ quả:

- Server ta gọi Twitch API bình thường → **vẫn dùng tốt làm tín hiệu dữ liệu**
- Nhưng nút "xem live" hướng tới người dùng VN **không** đặt Twitch làm trung
  tâm → ưu tiên YouTube và TikTok

## Việc cần làm, theo thứ tự

### 1. Thu thập chỉ số Steam

- `ISteamUserStats/GetNumberOfCurrentPlayers/v1/` — CCU từng game
- `ISteamChartsService/GetMostPlayedGames` — biết nên theo dõi game nào
- `store.steampowered.com/api/featuredcategories` với `cc=vn` — **bảng bán chạy
  tại VN**, dữ liệu gần như không ai làm
- `store.steampowered.com/appreviews/{appid}` — số review mới theo ngày

**Dùng chung token bucket với job giá ở Phase 2.** Giới hạn Steam tính theo IP,
không phải theo endpoint.

Không lấy dữ liệu từ SteamDB — họ không có API công khai và có chính sách
không cho scrape.

### 2. Twitch

- Helix `Get Streams` lọc `game_id` và `language` → ai đang stream game này
- **EventSub** `stream.online` / `stream.offline` → Twitch tự đẩy về server,
  không cần poll. Cần endpoint HTTPS công khai và xác thực chữ ký webhook.

### 3. YouTube — dùng WebSub, không dùng Data API search

Đăng ký PubSubHubbub trên feed từng kênh. YouTube đẩy thông báo khi kênh đăng
video hoặc mở live. **Không tốn quota Data API.**

Cần job gia hạn subscription định kỳ trước khi hết hạn — nếu quên thì thông
báo im lặng chết mà không báo lỗi.

Data API v3 chỉ dùng cho nhóm hot, nhớ quota 10.000 units/ngày và mỗi `search`
tốn 100.

### 4. Time-series và rollup

`game_metrics` là MongoDB time-series collection theo `SCHEMA.md`.

Rollup **bắt buộc làm ngay từ đầu**, không để dành tối ưu sau:

| Độ phân giải | Giữ |
|---|---|
| raw 15 phút | 7 ngày |
| gộp giờ | 90 ngày |
| gộp ngày (min/max/avg/peak) | vĩnh viễn |

### 5. Chỉ số hot

Chuẩn hoá từng kênh về **percentile trong cửa sổ 30 ngày** trước khi gán trọng
số. Không cộng thẳng số tuyệt đối — CCU đơn vị triệu, bài Reddit đơn vị trăm.

Hai bảng tách bạch:

- **Phổ biến nhất** — theo mức tuyệt đối
- **Đang tăng mạnh** — theo momentum, delta 24h và 7d

Bảng thứ hai mới là thứ người ta quay lại xem mỗi ngày. Nếu nó bị CS2/Dota 2
chiếm chỗ thì công thức sai.

Chống nhiễu chu kỳ: so sánh với **cùng kỳ tuần trước**, không phải hôm qua.
Gacha có nhịp banner, MMO reset tuần, mọi game đều tăng cuối tuần.

### 6. Streamer

Collection `streamers` theo `SCHEMA.md`. Theo dõi streamer, thông báo khi lên
sóng (một trong ba loại được đẩy tức thì).

**Danh sách streamer Việt phải curate tay** — không có nguồn tự động. Dựng
công cụ admin để thêm nhanh, và cho người dùng đề xuất kênh. Chính danh sách
này là tài sản khó sao chép nhất của sản phẩm.

### 7. Biểu đồ

Ba loại, theo thứ tự ưu tiên:

1. CCU theo thời gian **có overlay sự kiện** — ngày ra mắt, patch lớn, bắt đầu
   sale, ra DLC. Chính các mốc này biến đường lượn thành câu chuyện.
2. **Ghép giá và CCU trên cùng trục thời gian** — trả lời "đợt sale vừa rồi kéo
   được bao nhiêu người chơi". SteamDB không ghép hai thứ này.
3. Radar đa kênh — game hot vì có người chơi thật hay chỉ vì streamer.

## DỪNG LẠI ĐỂ REVIEW

Sau mục 4 (chính sách rollup) và sau mục 5 (công thức hot — trình bày kết quả
thử trên dữ liệu thật 2 tuần trước khi chốt).

## Checkpoint nghiệm thu

- [ ] Thu thập CCU 2.000 game hot mà không cạn quota Steam dùng chung với job giá
- [ ] Bảng "Đang tăng mạnh" không bị game top thường trực chiếm chỗ
- [ ] Push "streamer đang follow lên sóng" đến trong 60 giây
- [ ] Job gia hạn WebSub chạy đúng, subscription không hết hạn âm thầm
- [ ] Rollup chạy, dung lượng `game_metrics` ổn định sau 30 ngày
- [ ] Biểu đồ CCU + giá hiển thị đúng mốc sự kiện

## Sau khi xong

Cập nhật `PROGRESS.md`. Ghi lại số streamer Việt đã curate.
