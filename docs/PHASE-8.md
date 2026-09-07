# PHASE 8 — Cộng đồng & Giftcode

## Trước khi bắt đầu

Đọc `CLAUDE.md`, `PLAN.md`, `SCHEMA.md`, `PROGRESS.md`.
Xác nhận Phase 7 đã đạt checkpoint.

## Mục tiêu

Chuyển từ sản phẩm một chiều sang sản phẩm có cộng đồng — vừa giảm chi phí vận
hành, vừa tạo lý do để người dùng không rời đi.

## Việc cần làm

### 1. Giftcode và lịch banner game mobile

Traffic lớn nhất ở thị trường VN, không vướng bản quyền, rất hợp để đẩy thông
báo.

- Collection giftcode: game, mã, điều kiện, ngày hết hạn, nguồn, trạng thái
- Nguồn: trang chính thức của nhà phát hành, fanpage, và **đóng góp từ người
  dùng**
- Cho người dùng báo "mã đã hết hạn" → tự ẩn sau N lượt báo
- Lịch banner/sự kiện cho game gacha (dùng `is_live_service` và
  `current_season` đã có trong schema)
- Push khi giftcode sắp hết hạn — một trong ba loại đẩy tức thì

### 2. Đánh giá và điểm cộng đồng

- Người dùng chấm điểm + viết đánh giá
- **Ẩn hoàn toàn điểm cộng đồng cho tới khi đủ ≥ 20 lượt.** Giai đoạn đầu ít
  người, ba lượt chấm 10/10 sẽ phá niềm tin vào cả hệ thống
- Luôn hiện mẫu số: "7.8 (1.203 đánh giá)", không hiện điểm trần trụi
- Chống review bombing: chỉ tính tài khoản đã xác thực, làm mượt theo thời
  gian, gắn cờ khi có đột biến bất thường
- Điểm phê bình (nếu làm) tính bằng công thức trọng số riêng — **không** lấy
  con số tổng hợp của Metacritic

Hiển thị hai loại điểm song song, ghi nhãn rõ ràng, không trộn thành một số.

### 3. Mở hàng đợi duyệt cho cộng đồng

Cho người dùng: sửa tên tiếng Việt của game, thêm alias, gắn bài viết vào đúng
game, đề xuất kênh streamer, báo giftcode hết hạn.

Mọi đóng góp vẫn phải qua kiểm duyệt trước khi vào dữ liệu chính. Có nhật ký
để hoàn tác.

Badge và bảng ghi công đóng góp. **Gamification chỉ gắn vào đóng góp dữ liệu**
— không làm điểm ảo, không làm streak điểm danh. Thứ đó chỉ tạo số liệu đẹp giả.

### 4. Thống kê thư viện cá nhân

Dùng dữ liệu đã import từ Phase 3: số game sở hữu, số game chưa từng mở
(playtime = 0), tổng giờ chơi, DLC đang giảm giá của game đang có, ước tính đã
tiết kiệm bao nhiêu nhờ mua đúng đợt sale.

Loại thống kê này người ta chụp màn hình khoe rất nhiều — thiết kế để dễ chụp
và dễ chia sẻ.

### 5. Tổng kết cuối năm

Bản tóm tắt kiểu Wrapped, tái sử dụng đúng dữ liệu ở mục 4. Mỗi tháng 12 cho
một đợt lan truyền miễn phí.

Sinh ảnh chia sẻ bằng cùng cơ chế đã làm ở Phase 4.

## DỪNG LẠI ĐỂ REVIEW

Sau mục 2 (cơ chế chống review bombing) và sau mục 3 (luồng kiểm duyệt đóng
góp).

## Checkpoint nghiệm thu

- [ ] Game dưới 20 đánh giá → không hiện điểm cộng đồng
- [ ] Mô phỏng review bomb → hệ thống gắn cờ, điểm không nhảy đột ngột
- [ ] Đóng góp alias từ người dùng → qua duyệt → entity cập nhật, hoàn tác được
- [ ] Giftcode sắp hết hạn → push đến đúng người đang follow game đó
- [ ] Trang thống kê thư viện sinh được ảnh chia sẻ

## Sau khi xong

Cập nhật `PROGRESS.md`. Ghi lại số đóng góp cộng đồng mỗi tuần — nếu gần 0 thì
cơ chế khuyến khích ở mục 3 chưa hiệu quả.
