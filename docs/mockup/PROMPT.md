# Prompt giao việc cho Antigravity

Chép nguyên khối dưới đây. Cập nhật 2026-09-17, sau khi bốn endpoint đọc còn
thiếu đã được bổ sung — nay **không màn nào còn bị chặn bởi backend**.

---

# Nhiệm vụ: dựng nốt giao diện web GameNews (11 màn)

## Đọc trước khi viết dòng nào

- `docs/MOCKUP.md` — bản giao việc đầy đủ: 15 màn, trạng thái, hình dạng dữ
  liệu thật, ràng buộc cứng. **Đọc hết `§0` trước khi làm gì.**
- `docs/mockup/index.html` — mockup bấm được. Mở thẳng bằng trình duyệt.
- `docs/CLAUDE.md` — quy ước dự án. Luật vàng 1 và 2 áp dụng cho bạn.
- `docs/PROGRESS.md` — đọc 2 entry cuối để biết vừa có gì thay đổi.

Mọi con số trong `MOCKUP.md` đọc từ hệ thống chạy thật. Nếu bạn thấy dữ liệu
khác, **tin hệ thống chứ đừng tin tài liệu**, và ghi lại chênh lệch.

## Phạm vi: 11 màn còn lại, xếp theo thứ tự làm

4 màn đã xong (Deal, Miễn phí, Tin tức, Chi tiết game). 11 màn còn lại, tất cả
đều đã có API — **không màn nào cần bạn viết thêm backend**.

**Nhóm A — không cần đăng nhập, làm trước**

1. **Ô tìm kiếm trên nav + trang `/search`** — `GET /search?q=&page=`
2. **Ba khối của trang chi tiết game** (`MOCKUP.md §2.4`):
   - (a) bảng giá quốc tế — wiring đã có sẵn, chỉ cần render
   - (b) tin liên quan — `GET /news?game_id=`
   - (c) đánh giá cộng đồng — `GET /community/games/{id}/reviews/score` cho
     điểm, `GET /community/games/{id}/reviews` cho danh sách
3. **Trang chủ thật `/`** — hiện đang 302 sang `/deals`; thay bằng trang gom
   deal đáy lịch sử + game free + 5 tin mới + ô tìm kiếm lớn
4. **Trang thống kê `/thong-ke`** — `GET /dashboard/stats`, đúng 4 thẻ số
5. **Hồ sơ & huy hiệu `/nguoi-dung/:id`** — `GET /community/users/{id}/badges`

**Nhóm B — cần đăng nhập. Làm mục 6 trước, phần còn lại vô nghĩa nếu thiếu.**

6. **Đăng nhập Steam + trạng thái trên nav** — `GET /api/v1/auth/steam/login`
   (redirect), callback trả JWT. Lưu token, gắn `Authorization: Bearer` cho mọi
   lời gọi `/api/v1/user/*`, và hiện avatar/nút đăng xuất trên nav.
7. **Thư viện của tôi `/thu-vien`** — `GET /api/v1/user/library`
8. **Cảnh báo giá `/canh-bao`** — `GET` + `DELETE /api/v1/user/alerts/{id}`
9. **Đang theo dõi `/theo-doi`** — `GET` + `DELETE /api/v1/user/follows/{id}`
10. **Wrapped `/wrapped/:year`** — `GET /api/v1/user/me/wrapped/{year}`
11. **Nút đặt cảnh báo / theo dõi trên trang game** — `POST /alerts`,
    `POST /follows`

## Sáu điều dễ làm sai nhất — đọc kỹ

1. **`alerts[].owned == true`**: game đã có trong thư viện thì cảnh báo ấy
   **không bao giờ được gửi**. Phải **làm mờ kèm câu giải thích**, KHÔNG được
   ẩn — cảnh báo do chính người dùng đặt mà biến mất không lời nào thì họ chỉ
   đặt lại. Cờ này thuần trình bày; chặn gửi thật nằm ở backend.
2. **Danh sách đánh giá KHÔNG bị ngưỡng 20 chặn**, dù điểm trung bình thì có.
   Game 3 đánh giá vẫn hiện đủ 3 bài, mà chỗ điểm phải nói "chưa đủ lượt để
   tính điểm" — đừng để trống.
3. **`reviews[].user_id` là tất cả những gì có về người viết.** `users` chưa lưu
   tên hiển thị hay avatar. Render ô giữ chỗ ẩn danh, **đừng bịa tên**.
4. **`follows[].target` và `library[].game` có thể `null`** — mục không phải
   game, hoặc game đã bị gỡ khỏi catalog. Hiện `target_id` trần / tên mờ, đừng
   ẩn cả dòng.
5. **`DELETE` trả 404 khi mục không thuộc về mình** (cố ý không dùng 403). Giao
   diện chỉ cần hiện "không tìm thấy" rồi tải lại danh sách.
6. **Ảnh `null` là ca THƯỜNG, không phải ca hiếm.** `cover` và
   `cover_image_url` null rất nhiều — kể cả Elden Ring. Mọi chỗ hiện ảnh phải
   có nhánh vắng mặt. Trang `/free` từng hiện ảnh vỡ đúng vì quên điều này.

## Ràng buộc cứng — vi phạm là lỗi pháp lý, không phải lỗi giao diện

1. **Không bao giờ render `articles.original_content`.** Nó giữ nguyên văn HTML
   bài gốc. API `/news` đã chặn hai lớp và không trả trường đó — đừng mở đường
   nào để lấy ra. Thẻ tin chỉ được có: tiêu đề đã dịch, tóm tắt tự viết, tên
   nguồn, link ra bài gốc.
2. Không hiện điểm tổng hợp Metacritic.
3. Không bao giờ hiện cảnh báo giảm giá cho game người dùng đã sở hữu (xem
   điều 1 mục trên).
4. Thư viện chỉ có appid + playtime + mốc đồng bộ. **Không lịch sử mua.**
5. Giá CheapShark là **USD dạng cent** — không trộn vào bảng giá VND. Trộn là
   render "51.59" thành "52₫".

## Quy ước code

- Angular standalone components, Tailwind, nền tối. Bảng màu ở `MOCKUP.md §0`.
- Dùng lại `app-nav` (`web/src/app/components/nav/`). Thêm mục mới vào mảng
  `muc` trong `nav.component.ts`, **đừng chép lại thanh nav**.
- Service theo mẫu `web/src/app/services/news.service.ts`: inject
  `API_BASE_URL`, dùng `HttpParams` chứ đừng nối chuỗi.
- **Mỗi màn phải có đủ ba trạng thái**: đang tải, rỗng (nói rõ vì sao rỗng),
  lỗi (kèm nút thử lại). Với "xem thêm" thì tách cờ riêng để không chớp trắng
  cả danh sách — xem `dangTaiThem` trong `news.component.ts`.
- Phân trang so với `total` của API, **đừng so độ dài trang với `limit`** —
  cách sau sai đúng ở ca trang cuối vừa tròn.
- Comment bằng tiếng Việt, giải thích **vì sao** chứ không mô tả lại code.

## Nghiệm thu — chạy thật, đừng chỉ tin test

```bash
# Python (không đụng tới trong lượt này, nhưng phải còn xanh)
uv run ruff check . && uv run mypy app tests && uv run pytest

# Test web — BẮT BUỘC dùng launcher no-sandbox, Chrome không chạy nổi
# trong container nếu thiếu cờ này
docker run --rm -v "$PWD/web:/w" -w /w -e CHROME_BIN=/usr/bin/chromium-browser \
  node:22-alpine sh -c "apk add --no-cache chromium >/dev/null 2>&1 && \
  npx ng test --watch=false --browsers=ChromeHeadlessNoSandbox"

# Dựng lại và xem thật — `restart` KHÔNG nạp code mới, phải `--build`
docker compose up -d --build web
```

Sau đó **mở trình duyệt xem từng màn**. Test xanh không chứng minh giao diện
đúng: trang `/free` từng xanh mọi cổng trong khi hiển thị một game bịa với ảnh
chết.

Với mỗi test mới: **xác minh nó ĐỎ khi gỡ bản sửa ra**. Test xanh mà chưa bao
giờ đỏ thì không chứng minh gì. Và khi gỡ, hãy đọc output để chắc lệnh gỡ **thật
sự đã chạy** — một lệnh hỏng làm test xanh, và xanh ở đó là kết quả tệ nhất vì
nó trông đúng như điều mình muốn thấy.

## Commit

Một commit cho mỗi màn, đừng gộp. Message tiếng Việt, mô tả **vì sao** thay đổi
và cái gì đã được nghiệm thu. Kết thúc bằng:

```
Co-Authored-By: Claude <noreply@anthropic.com>
```

Làm trên nhánh riêng, đừng commit thẳng vào `main`.

## Khi bí

Nếu một yêu cầu mâu thuẫn với tài liệu, hoặc cần một nguồn/dịch vụ chưa có
trong `DATA-SOURCES.md` — **dừng và hỏi**, đừng tự quyết. Đặc biệt: đừng tự
thêm endpoint backend nào. Nếu thiếu dữ liệu, báo lại.
