# Bàn giao lượt 2 — phần web còn thiếu

Tài liệu giao việc cho agent ngoài (antigravity). Người viết sẽ **review lại
toàn bộ code** trước khi merge.

Đọc kèm: `CLAUDE.md` (quy ước), `PROGRESS.md` lượt 11–14 (bối cảnh gần nhất).

---

## 0. Vì sao tài liệu này viết chặt như vậy

Lượt bàn giao trước (`docs/MOCKUP.md` → commit `68605e4`) trả về 1.513 dòng,
31 file. Kết quả khi kiểm:

- **Không biên dịch được.** `app.routes.ts` dùng `SearchComponent` mà không
  import. Tức chưa ai chạy `npm run build` lấy một lần.
- **Sáu endpoint được bịa ra**: `/auth/login`, `/auth/register`, `/me`,
  `/me/follows`, `/me/watchlist`, `/me/wrapped`. Tất cả 404.
- **Sai hợp đồng dữ liệu**: `WrappedData` khai `total_hours`, `top_genre`,
  `top_game` trong khi backend trả `total_playtime_minutes`, `top_games`,
  `message`.

Điểm nguy hiểm nhất: **ba service khác lại đúng từng trường**. Đúng một phần
nên đọc lướt vài file không phát hiện được.

Nên phần §2 và §3 dưới đây không phải gợi ý. Không đạt thì không merge.

---

## 1. Ba điều tuyệt đối không làm

**1. Không bịa endpoint.** Mọi đường dẫn phải có trong `/openapi.json` của
backend đang chạy. Cách kiểm:

```bash
curl -s localhost:8000/openapi.json | jq -r '.paths | keys[]'
```

Không thấy đường mình định gọi ở đó thì **dừng và hỏi**, đừng tự tạo.

**2. Không mock.** Không `MockXxx`, không dữ liệu viết cứng giả làm dữ liệu
thật, không `setTimeout` giả lập hành vi người dùng. Mock bên Flutter
(`MockFirebaseMessaging`, đã xoá ở lượt 14) không chỉ trả token giả mà còn tự
điều hướng người dùng sang `/game/elden-ring` sau 15 giây trong **mọi** bản
build. Thiếu dữ liệu thì để trạng thái rỗng trung thực, hoặc hỏi.

**3. Không nói sai trên giao diện.** Trang trống thì người dùng biết là chưa
có gì; trang hiển thị số liệu sai thì tệ hơn nhiều. Nhãn phải khớp đúng ngữ
nghĩa backend — ví dụ `below_price` là `price_final <= value`, nên viết "còn X
hoặc thấp hơn", không phải "dưới X".

---

## 2. Cổng nghiệm thu

Một hạng mục **chưa xong** nếu bốn job CI chưa xanh. Chạy được ở local trước
khi push:

| cổng | lệnh |
|---|---|
| web build | `cd web && npm run build` |
| web test | `cd web && npx ng test --watch=false --browsers=ChromeHeadlessNoSandbox` |
| python | `uv run ruff check . && uv run mypy app tests && uv run pytest` |
| mobile | `cd mobile && flutter analyze` |

`npm run build` dùng cấu hình **production** — bản development xanh không suy
ra production xanh.

Thêm nữa, mỗi hạng mục phải:

- **Có test đi kèm**, và test ấy phải **đỏ khi gỡ bản sửa ra**. Test xanh trên
  code sai thì không chứng minh gì. Xem
  `web/src/app/services/api-paths.spec.ts` làm mẫu.
- **Chạy thật một lần**: mở trình duyệt vào trang vừa làm, xem log backend
  không có 404/422 nào phát sinh. SSR trả HTTP 200 **kể cả khi** lời gọi API
  bên trong hỏng — component nuốt lỗi vào `error:` — nên mã trạng thái của
  trang không phải bằng chứng.

---

## 3. Hợp đồng API — chép từ `/openapi.json`, không viết lại từ trí nhớ

Mọi endpoint dưới đây **đã tồn tại và đã chạy**. Không sửa backend.

Nhóm `/api/v1/user/*` đòi `Authorization: Bearer <JWT>`;
`AuthInterceptor` đã tự gắn, không tự thêm header.

| endpoint | method | body / params | trả về |
|---|---|---|---|
| `/api/v1/user/follows` | POST | `{target_type, target_id}` | `{status, followed}` |
| `/api/v1/user/follows` | GET | — | `{follows[], total}` |
| `/api/v1/user/follows/{follow_id}` | DELETE | — | `{status}` |
| `/api/v1/user/library` | GET | `?limit=50&offset=0` | `{items[], total, limit, offset}` |
| `/api/v1/user/library/sync` | POST | — | `{synced, skipped}` |
| `/api/v1/user/library` | DELETE | — | `{deleted_count}` |
| `/community/reviews` | POST | `{game_id, score}` + `comment?` | — |
| `/community/users/{user_id}/badges` | GET | — | `[]` |
| `/news` | GET | `?limit&offset&game_id` | `{articles[], ...}` |

Chi tiết các kiểu hay sai:

- `target_type` là `Literal["game","series","developer","streamer"]`. Gửi giá
  trị khác → **422**.
- `target_id` của game là **ObjectId dạng chuỗi**; của series/streamer là slug
  hoặc tên. Backend tự phân biệt theo `target_type`.
- `score` của review là **số nguyên**. `comment` được phép `null`.
- **Không gửi `user_id`** trong bất kỳ body nào. Chủ sở hữu lấy từ JWT; các
  model request đã bỏ hẳn trường đó ở lượt 11.
- `items[]` của library: `{game_id, store, playtime_minutes, synced_at, game}`,
  trong đó `game` là `{title, slug, cover_image_url}` hoặc `null`.
- `follows[]`: `{id, target_type, target_id, target}`. `target` là `null` với
  mọi mục **không phải game** — đó là trạng thái bình thường, không phải lỗi
  tải. Hiển thị bằng `target_id` trần.

---

## 4. Hạng mục

Làm theo thứ tự. Mỗi mục là một commit riêng.

### 4.1 Nút "Theo dõi" ở trang game — **ưu tiên cao nhất**

**Vấn đề:** `POST /api/v1/user/follows` chưa được gọi từ bất cứ đâu trong web.
Trang `/follows` chỉ **xoá** được. Nghĩa là nó vĩnh viễn rỗng — không có đường
nào tạo ra một mục để mà xem.

**Việc:** thêm nút bật/tắt theo dõi ở `web/src/app/pages/game/`, cùng cụm với
hai nút cảnh báo đang có.

**Xong khi:** theo dõi từ trang game → mục hiện ra ở `/follows` kèm ảnh bìa và
tên game → bỏ theo dõi từ cả hai nơi đều được.

**Cạm bẫy:** `POST /follows` là upsert và trả `{status, followed}` — **không có
`_id`**. Muốn xoá thì phải `GET /follows` đọc lại lấy `id`. Đây đúng là điều
`game.component.ts` đã làm cho cảnh báo giá (`napCanhBao`), xem lại chỗ đó.

### 4.2 Thư viện Steam

**Việc:** trang `/thu-vien` + thẻ dẫn ở `/profile`.

- `GET /api/v1/user/library` — danh sách, sắp theo `playtime_minutes` giảm dần
  (backend đã sắp sẵn), phân trang qua `limit`/`offset`.
- `POST /api/v1/user/library/sync` — nút "Đồng bộ từ Steam".
- `DELETE /api/v1/user/library` — nút xoá, **phải có bước xác nhận**.

**Cạm bẫy — quan trọng:** `sync` trả **403** với `detail: "PROFILE_IS_PRIVATE"`
khi profile Steam không công khai. Đây là ca thường gặp nhất, không phải ca
hiếm. Phải hiện màn hình hướng dẫn mở profile, không phải "Lỗi, thử lại sau".
Có sẵn `docs/STEAM_PROFILE_GUIDE.md`.

**Xong khi:** đồng bộ → thấy game; profile private → thấy hướng dẫn đúng;
`{synced: 0, skipped: N}` hiển thị ra được, không nuốt im.

### 4.3 Viết đánh giá

**Việc:** form nhập điểm + bình luận ở trang game, gọi `POST /community/reviews`.

**Cạm bẫy:**

- Điểm ẩn khi dưới ngưỡng: `GET .../reviews/score` trả
  `{is_hidden: true, average_score: null}` khi chưa đủ 20 lượt. Giao diện phải
  nói "chưa đủ lượt đánh giá", **không** hiển thị `null` thành `0`.
- Gửi xong phải đọc lại danh sách; đừng tự chèn vào mảng local rồi coi là xong.

### 4.4 Huy hiệu ở trang cá nhân

`GET /community/users/{user_id}/badges`. `user_id` lấy từ `SteamSession.user_id`.
Hiện trả `[]` — badge chỉ sinh ra sau khi có người viết đánh giá, nên **làm sau
4.3** để còn dữ liệu mà kiểm.

### 4.5 Lọc tin theo game

`GET /news` đã nhận `game_id` và `news.service.ts` đã truyền được. Thiếu mỗi
phần giao diện chọn game ở trang `/news`.

---

## 5. Việc KHÔNG giao — và vì sao

Đừng làm những mục này. Chúng bị chặn ở tầng dữ liệu hoặc cần quyết định của
chủ dự án.

| mục | lý do |
|---|---|
| Banner khuyến mãi | Collection `banners` **không có writer nào** trong cả codebase — chỉ có hàm đọc. Dựng giao diện cho dữ liệu vĩnh viễn rỗng thì không nghiệm thu được. Cần quyết định nguồn dữ liệu trước. |
| Giftcode | Y hệt: `giftcodes` chỉ có hàm đọc. |
| `POST /library/epic/bulk` | Backend trả **501** có chủ đích. Cần job catalog Epic đánh dấu game từng free theo tuần trước đã. |
| Thông báo đẩy | Đã dựng xong ở lượt 13–14, đang chờ 5 giá trị Firebase. Không đụng vào. |
| Sửa backend | Ngoài phạm vi lượt này. Thiếu gì thì hỏi. |

---

## 6. Quy ước repo

- Angular standalone component, SSR luôn bật.
- Tên biến/hàm mới **tiếng Việt không dấu** theo lệ đang có (`dangTai`,
  `napCanhBao`, `moTaDieuKien`). Đừng trộn thêm lối đặt tên thứ ba.
- Chú thích giải thích **vì sao**, không phải *cái gì*. Chỗ nào từng sai thì
  ghi lại cái sai đó — đó là lệ của repo này, xem
  `web/src/app/services/alert.service.ts`.
- Mọi lời gọi API đi qua một service trong `web/src/app/services/`. Component
  không tự gọi `HttpClient`.
- `API_BASE_URL` inject qua token, **không** đọc thẳng `environment.apiUrl`
  trong service — SSR và browser dùng hai địa chỉ khác nhau.
- Phân biệt **401** (mời đăng nhập) với **lỗi tải** (báo hỏng). Gộp hai ca là
  lỗi đã sửa ở lượt 11, đừng tái lập.
