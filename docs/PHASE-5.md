# PHASE 5 — Mobile

## Trước khi bắt đầu

Đọc `CLAUDE.md`, `PLAN.md`, `PROGRESS.md`. Xác nhận Phase 4 đã đạt checkpoint.

## Mục tiêu

App Flutter cho Android và iOS, dùng lại toàn bộ API đã có. Không viết logic
nghiệp vụ mới ở client.

## Phạm vi

**LÀM:** Flutter app, auth, thư viện, follow, cảnh báo giá, push, deep link,
widget/Live Activity, đăng ký store.

**KHÔNG LÀM:** tính năng chỉ có trên app mà web không có. Mọi thứ phải tương
đương, khác biệt duy nhất là push và widget.

## Việc cần làm

### 1. Khung app

Flutter, một codebase. State management chọn cái đơn giản, không cần kiến trúc
nặng. Client API sinh từ OpenAPI schema của FastAPI.

### 2. Màn hình

Trang chủ (deal + free tuần này), tìm kiếm, chi tiết game, thư viện cá nhân,
cảnh báo, cài đặt thông báo.

Ưu tiên trang chi tiết game và trang deal — đó là nơi người dùng ở lâu nhất.

### 3. Push

FCM. Xử lý cả ba trạng thái: foreground, background, terminated. Bấm vào thông
báo phải mở đúng trang game, không phải trang chủ.

### 4. Deep link

Link web mở được trong app nếu đã cài (App Links trên Android, Universal Links
trên iOS). Đây là cầu nối giữa kênh tăng trưởng (web) và kênh giữ chân (app).

### 5. Widget và Live Activity

Widget Android + Live Activity iOS cho: đếm ngược game sắp ra mắt, deal đang
theo dõi. Làm sau khi các màn hình chính đã ổn.

### 6. Đăng ký store

Apple Developer Program (99 USD/năm) và Google Play Console (25 USD một lần).
Chuẩn bị: chính sách quyền riêng tư (phải nêu rõ ta lấy gì từ Steam và lưu bao
lâu), ảnh chụp màn hình, mô tả tiếng Việt và tiếng Anh.

Lưu ý cả hai store đều xét duyệt kỹ phần khai báo thu thập dữ liệu. Khai đúng
những gì `user_library` thực sự lưu.

## DỪNG LẠI ĐỂ REVIEW

Sau mục 2 (danh sách màn hình và điều hướng) và trước khi nộp store lần đầu.

## Checkpoint nghiệm thu

- [ ] Build lên TestFlight và Google Play Internal Testing
- [ ] Chạy được trên máy thật cả hai nền tảng
- [ ] Nhận push đúng ở cả ba trạng thái app
- [ ] Bấm thông báo mở đúng trang game
- [ ] Dán link web vào tin nhắn → mở trong app
- [ ] Khai báo quyền riêng tư khớp với dữ liệu thực sự lưu

## Sau khi xong

Cập nhật `PROGRESS.md`. Ghi lại ngày hết hạn Apple Developer để gia hạn.
