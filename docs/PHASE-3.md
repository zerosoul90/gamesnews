# PHASE 3 — Người dùng & Thông báo

## Trước khi bắt đầu

Đọc `CLAUDE.md`, `PLAN.md`, `DATA-SOURCES.md`, `SCHEMA.md`, `PROGRESS.md`.
Xác nhận Phase 2 đã đạt checkpoint.

## Mục tiêu

Người dùng liên kết được tài khoản Steam, đặt được cảnh báo giá, và nhận thông
báo đúng lúc mà không bị làm phiền.

## Nguyên tắc bất di bất dịch

**Không bao giờ gửi cảnh báo giảm giá cho game người dùng đã sở hữu.** Đây là
lý do chính đáng duy nhất để họ chịu mở public profile, và là ranh giới giữa
thông báo hữu ích với spam.

## Việc cần làm, theo thứ tự

### 1. Auth

Đăng nhập bằng Steam OpenID. Người dùng **không** đưa mật khẩu cho ta, luồng
chỉ trả về SteamID64. Ngoài ra một phương thức đăng nhập độc lập (email hoặc
OAuth) để không bắt buộc phải có Steam.

### 2. Import thư viện và wishlist

Gọi từ server bằng Steam Web API key:

- `IPlayerService/GetOwnedGames/v1/` — appid + playtime
- `IWishlistService/GetWishlist/v1/` — **chỉ trả appid, priority, date_added**,
  phải tra ngược tên từ catalog của mình

Endpoint cũ `store.steampowered.com/wishlist/profiles/{id}/wishlistdata/` đã bị
bỏ, không dùng.

Chỉ lưu `appid`, `playtime_minutes`, `synced_at`. Không lưu lịch sử mua, không
lưu gì hơn mức cần. Có nút xoá toàn bộ thư viện đã đồng bộ.

### 3. Xử lý profile private — đây là chỗ rớt người dùng nhiều nhất

Steam chỉ trả dữ liệu khi "Game details" ở chế độ Public. Mặc định nhiều tài
khoản không public.

Cần: phát hiện được trường hợp private và phân biệt với lỗi mạng; màn hình
hướng dẫn từng bước có ảnh chụp; nút "kiểm tra lại" tự động thay vì bắt người
dùng bấm thử nhiều lần; và giải thích rõ ta lấy gì, để làm gì.

### 4. Epic — tick nhanh

Epic **không** có API cho bên thứ ba đọc thư viện. Không dùng đường không
chính thức (Legendary hay tương tự) — vi phạm ToS và rủi ro khoá tài khoản
người dùng.

Thay bằng: màn hình liệt kê game free hàng tuần của Epic theo thời gian (dữ
liệu đã có từ Phase 2), cho tick nhanh, kèm nút "tôi nhận đều từ tháng X/năm Y"
để đánh dấu hàng loạt.

### 5. Follow và cảnh báo

Follow: game, series, developer, platform.

`price_alerts` với ba loại điều kiện: dưới một mức giá, giảm từ X% trở lên,
chạm đáy lịch sử. Kiểm tra ngay trong luồng cập nhật giá của Phase 2, không
làm job quét riêng.

### 6. Thông báo

Firebase Cloud Messaging.

Đẩy **tức thì** chỉ ba loại: giá chạm ngưỡng đã đặt, streamer đang follow lên
sóng (Phase 7), giftcode sắp hết hạn (Phase 8).

Mọi thứ còn lại **gộp thành digest** theo ngày.

Bắt buộc có: giờ im lặng ban đêm, bật/tắt riêng từng loại, và chống gửi trùng
(một game giảm giá không được bắn hai lần vì hai job khác nhau).

## DỪNG LẠI ĐỂ REVIEW

Sau mục 3 (luồng xử lý profile private) và sau mục 6 (thiết kế chống spam).

## Checkpoint nghiệm thu

- [ ] Đăng nhập Steam, import đúng thư viện và wishlist
- [ ] Profile private → hiện hướng dẫn đúng, không báo lỗi kỹ thuật
- [ ] Đặt cảnh báo, giá chạm ngưỡng → nhận push trong 15 phút
- [ ] Game đã sở hữu giảm giá → **không** nhận bất kỳ thông báo nào
- [ ] Trong giờ im lặng → thông báo bị hoãn, không mất
- [ ] Bấm xoá thư viện → dữ liệu biến mất hoàn toàn khỏi DB

## Sau khi xong

Cập nhật `PROGRESS.md`. Ghi lại tỉ lệ người dùng thử nghiệm chịu mở public
profile — nếu quá thấp thì luồng hướng dẫn ở mục 3 cần làm lại.
