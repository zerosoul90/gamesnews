# PHASE 4 — Web công khai & SEO

## Trước khi bắt đầu

Đọc `CLAUDE.md`, `PLAN.md`, `PROGRESS.md`. Xác nhận Phase 3 đã đạt checkpoint.

**Chặn:** framework web phải được chốt trước (Angular vs Next.js/Nuxt). Nếu
`PROGRESS.md` chưa tick mục này thì DỪNG và hỏi tôi.

## Mục tiêu

Web là kênh tăng trưởng chính, không phải phần phụ của app. Người dùng đến từ
Google và từ link chia sẻ trong group Facebook.

## Nguyên tắc

**Web phải dùng được đầy đủ mà không cần cài app.** Không có tường chặn, không
có popup ép tải app. App tồn tại để nhận thông báo, không phải để làm cổng gác.

## Việc cần làm, theo thứ tự

### 1. SSR

Nội dung phải có sẵn trong HTML trả về từ server. Tắt JavaScript vẫn đọc được
đủ nội dung trang game.

### 2. Trang game — trả lời sẵn bốn câu hỏi người Việt gõ Google

Nội dung tĩnh, sinh tự động từ dữ liệu đã có, không viết tay:

- "X có chơi được máy yếu không" → so cấu hình tối thiểu/đề nghị, kèm form cho
  người dùng nhập cấu hình máy mình (lưu lại một lần, dùng cho mọi game sau)
- "X giá bao nhiêu Steam" → giá VND hiện tại, đáy lịch sử, biểu đồ 30 ngày
- "X ra ngày nào" → release date theo region, đếm ngược nếu chưa ra
- "mua X ở đâu" → so giá các store, cảnh báo nếu khoá khu vực VN

### 3. Trang deal và free tuần này

Sắp theo chất lượng deal. Lọc theo mức giá, theo store, theo thể loại.

### 4. Thẻ chia sẻ dạng ảnh

Sinh phía server (Pillow hoặc Satori). Mỗi game, mỗi deal có một ảnh chứa: tên
game, giá VND, % giảm, có phải đáy lịch sử không, logo, tên miền.

Đây là cơ chế lan truyền rẻ nhất — người ta đăng ảnh lên group thay vì gõ lại
thông tin. Phải render đúng khi dán link vào Facebook và Zalo.

### 5. SEO kỹ thuật

Sitemap phân mảnh (catalog lớn), structured data (VideoGame, Offer,
AggregateRating), i18n route với hreflang, canonical URL, meta mô tả sinh tự
động từ dữ liệu.

### 6. Analytics

Umami self-host. Không có nó thì sáu tháng nữa vẫn đoán mò nên đầu tư vào đâu.

## DỪNG LẠI ĐỂ REVIEW

Sau mục 2 (bố cục trang game) — đây là trang quyết định toàn bộ SEO. Trình bày
wireframe và cấu trúc heading trước khi code.

## Checkpoint nghiệm thu

- [ ] Lighthouse SEO ≥ 90 trên trang game
- [ ] Tắt JavaScript → trang game vẫn đọc được đủ nội dung
- [ ] Dán link vào Facebook và Zalo → thẻ chia sẻ hiện đúng ảnh và mô tả
- [ ] Sitemap hợp lệ, Google Search Console không báo lỗi cấu trúc
- [ ] Không có popup hay tường chặn ép tải app
- [ ] Umami ghi nhận được pageview

## Sau khi xong

Cập nhật `PROGRESS.md`. Nộp sitemap lên Google Search Console và ghi lại ngày
nộp — cần vài tuần mới thấy hiệu quả.
