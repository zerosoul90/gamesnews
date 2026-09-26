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

- **F1 — backend + test.** ✅ `94979c6`. Biệt danh, chuyên mục, chủ đề, trả
  lời, báo cáo, chặn tần suất, cổng beta.
- **F2 — web.** ✅ `de14723`. `/forum`, `/forum/c/:slug`, `/forum/t/:id`,
  form đặt biệt danh. SSR, lazy-load.
- **F3 — kiểm duyệt + trang game.** ✅ `/admin/forum` (hàng đợi, khôi phục /
  gỡ / khoá, cấp quyền beta, nhật ký `forum_mod_log`); `/forum/g/:gameSlug`
  và mục "Thảo luận" trên trang game.

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
  người khác nhau thì bài tự ẩn chờ admin. Admin khôi phục hoặc gỡ thì báo
  cáo đang treo được đóng (`resolved`) — không đóng thì một báo cáo mới là
  đủ ẩn lại bài vừa khôi phục.
- **Trạng thái bài**: `visible` · `hidden` (tự ẩn vì báo cáo) · `deleted`
  (người viết tự xoá) · `removed` (admin gỡ). `reply_count` chỉ đếm `visible`.

## Vận hành beta

Cấp quyền đăng bài: người đó đăng nhập bằng Steam một lần, rồi admin nhập
`steam_id64` ở `/admin/forum`. Cần `ADMIN_TOKEN` trong `.env` — để trống thì
toàn bộ `/admin` trả 503.

Mở công khai: đặt `FORUM_OPEN=true`. **Chỉ sau khi đã chốt pháp lý.**

## Cổng đăng bài

Đọc: công khai. Đăng (chủ đề, trả lời, báo cáo) cần cả bốn:

1. JWT hợp lệ
2. `settings.forum_open` bật, **hoặc** `users.forum_access = true` (admin cấp)
3. Đã đặt biệt danh
4. Còn token trong bucket: 5 chủ đề/giờ, 30 trả lời/giờ, 20 báo cáo/giờ
