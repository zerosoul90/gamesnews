# FORUM.md — Diễn đàn trao đổi về game

Tính năng **ngoài `PLAN.md`**, người dùng yêu cầu ngày 2026-09-26. Gần nhất
với Phase 8 (cộng đồng), nhưng không thay thế mục nào của Phase 8.

## Quyết định đã chốt (2026-09-26)

| Câu hỏi | Chốt |
|---|---|
| Pháp lý (NĐ 147/2024: xác thực SĐT với mạng xã hội) | **Beta kín.** Ai cũng đọc được; chỉ người được cấp quyền mới đăng. Chủ dự án tự kiểm pháp lý trước khi mở công khai — xác thực SMS tốn tiền, vướng luật vàng số 5 |
| Cấu trúc | Chuyên mục chung (JSON tĩnh) **và** khu thảo luận theo từng game |
| Danh tính | **Biệt danh tự đặt**, không dùng tên Steam |
| Người làm | Claude trực tiếp, dừng review sau mỗi chặng |

## Chặng

- **F1 — backend + test.** Biệt danh, chuyên mục, chủ đề, trả lời, báo cáo,
  chặn tần suất, cổng beta. *Dừng review.*
- **F2 — web.** `/forum`, `/forum/c/:slug`, `/forum/t/:id`, form đặt biệt danh.
  SSR. *Dừng review.*
- **F3 — kiểm duyệt + trang game.** Hàng đợi bài bị báo cáo ở trang admin, tab
  "Thảo luận" trên trang game.

Ngoài MVP: mobile, thông báo có người trả lời, tìm kiếm chủ đề, reaction.

## Luật dữ liệu

- **Biệt danh**: 3–24 ký tự sau khi gộp khoảng trắng; chữ (kể cả tiếng Việt),
  số, khoảng trắng, `_ . -`. Khoá duy nhất là `normalize_vi` bỏ khoảng trắng —
  "Trần Văn" và "tranvan" là **một** tên, để chặn giả danh bằng dấu. Danh sách
  tên cấm ở `app/services/forum_reserved_names.json`. Đổi tối đa 30 ngày một
  lần.
- **Nội dung là text thuần.** Server không render HTML; web hiển thị bằng nội
  suy Angular (tự escape). Không bao giờ `innerHTML`.
- **Không lộ `steam_id64`** ra API diễn đàn — chỉ `user_id` và biệt danh.
- **Xoá là xoá mềm** (`status = "deleted"`), để kiểm duyệt còn tra được.
- **Báo cáo**: mỗi người một lần cho mỗi bài. Đủ `REPORT_HIDE_THRESHOLD` (3)
  người khác nhau thì bài tự ẩn chờ admin.

## Cổng đăng bài

Đọc: công khai. Đăng (chủ đề, trả lời, báo cáo) cần cả bốn:

1. JWT hợp lệ
2. `settings.forum_open` bật, **hoặc** `users.forum_access = true` (admin cấp)
3. Đã đặt biệt danh
4. Còn token trong bucket: 5 chủ đề/giờ, 30 trả lời/giờ, 20 báo cáo/giờ
