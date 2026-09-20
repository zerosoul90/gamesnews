# Bàn giao lượt 3 — theo dõi mở rộng, và dọn nợ lượt 2

Tài liệu giao việc cho agent ngoài (antigravity). Người viết sẽ **review lại
toàn bộ code** trước khi merge.

Đọc kèm: `CLAUDE.md` (quy ước), `HANDOFF-2.md` (lượt trước — §1 và §3 vẫn còn
hiệu lực nguyên vẹn), `PROGRESS.md` lượt 15.

---

## 0. Lượt trước đạt được gì, và trượt ở đâu

Đọc kỹ phần này. Nó quyết định §2 và §3 dưới đây viết như vậy.

**Đã khá lên thật.** Commit `2bb2a3b` (11 file, 581 dòng) có bốn cổng CI xanh,
không một `Mock` nào, và — quan trọng nhất — **cả 6 endpoint mới đều có thật**.
Lượt 11 bịa ra sáu đường 404; lượt 2 không bịa đường nào. `api-paths.spec.ts`
đã làm đúng việc của nó.

**Nhưng ba lỗi vẫn lọt, và cả ba đều xanh ở mọi cổng:**

1. **Hợp đồng dữ liệu bịa.** `Badge` khai `name`, `description`, `icon_url`.
   Không trường nào tồn tại — `UserBadge` chỉ có `user_id`, `badge_type`,
   `earned_at`. Trang cá nhân in ra một lưới ô xám: không ảnh, tiêu đề rỗng,
   mô tả rỗng.

2. **Một dòng gán đè lên chính mình.** `dongBo()` gán `dongBoKetQua = res` rồi
   gọi ngay `tai()`, mà `tai()` mở đầu bằng `dongBoKetQua = null`. Băng rôn
   không hiện lần nào.

3. **`routerLink="/auth"`** — route không tồn tại. Rơi vào `**`, mở trang 404.

### Bài học số một: `/openapi.json` không đủ

Lỗi 1 **không thể** bắt bằng cách đối chiếu URL. Endpoint ấy khai
`-> list[dict[str, Any]]`, nên OpenAPI ghi schema rỗng — không có gì để so.

> Đối chiếu **đường dẫn** và đối chiếu **hình dạng phản hồi** là hai việc khác
> nhau. Việc thứ hai không có công cụ tự động nào; nguồn sự thật là model
> Pydantic trong `app/models/`, hoặc gọi thật endpoint đó.

Collection rỗng nên không gọi thử được? Vẫn kiểm được, rẻ:

```bash
docker exec gamesnews-mongo-1 mongosh --quiet --eval '
  db.getSiblingDB("gamesnews").user_badges.insertOne({
    user_id: ObjectId("0000000000000000deadbeef"), badge_type: "reviewer",
    earned_at: "2026-09-01T10:00:00+00:00"})'

curl -s localhost:8000/community/users/0000000000000000deadbeef/badges

docker exec gamesnews-mongo-1 mongosh --quiet --eval '
  db.getSiblingDB("gamesnews").user_badges.deleteMany({
    user_id: ObjectId("0000000000000000deadbeef")})'
```

Chèn — gọi — xoá. Ba dòng, và nó trả lời dứt khoát câu hỏi mà đọc code chỉ trả
lời được "chắc là".

### Bài học số hai: Angular không bao giờ kêu vì liên kết sai

Route `**` ở cuối `app.routes.ts` khớp mọi thứ. `routerLink` nhận chuỗi bất kỳ.
Build xanh, SSR trả 200, người dùng ra trang 404. Nay đã có
`routes.spec-util.ts::duongDanCoThat()` để chốt — **dùng nó** cho mọi liên kết
nội bộ mới.

### Bài học số ba: test phải đỏ được

Lượt 2 thêm 581 dòng và **không một test nào**. Số test trước và sau đều là 28.

---

## 1. Ba điều tuyệt đối không làm

Giữ nguyên từ `HANDOFF-2.md` §1, không nhắc lại: **không bịa endpoint**,
**không mock**, **không nói sai trên giao diện**. Đọc lại nếu quên.

Lượt này thêm điều thứ tư:

**4. Không khai một trường mà chưa nhìn thấy nó trong phản hồi thật.** Không
đoán từ tên endpoint, không suy từ trang tương tự, không chép từ một API khác.
Chưa gọi được thì hỏi, đừng khai bừa rồi để giao diện in ra ô trống.

---

## 2. Cổng nghiệm thu

Bốn job CI như cũ:

| cổng | lệnh |
|---|---|
| web build | `cd web && npm run build` |
| web test | `cd web && npx ng test --watch=false --browsers=ChromeHeadlessNoSandbox` |
| python | `uv run ruff check . && uv run mypy app tests && uv run pytest` |
| mobile | `cd mobile && flutter analyze` |

**Chạy từ đúng thư mục và in mã thoát ra.** Lượt 15 có một lần `ng test` chạy
sai thư mục, trả về không một dòng nào, và output rỗng trông y hệt "mọi thứ
đều xanh". Kết thúc lệnh bằng `; echo "EXIT=$?"`.

Thêm nữa, mỗi hạng mục phải:

- **Một hạng mục, một commit.** Lượt 2 gộp cả 5 mục vào một commit tên tiếng
  Anh. Message viết tiếng Việt, nói **vì sao**, không liệt kê file.
- **Có test đi kèm, và test ấy phải đỏ khi gỡ bản sửa ra.** Cách kiểm: sửa
  ngược code về bản sai, chạy test, xem thông báo đỏ có đúng triệu chứng
  không, rồi revert. Nếu test vẫn xanh trên code sai thì nó không chứng minh
  gì. Xem bảng ở `PROGRESS.md` lượt 15 làm mẫu.
- **Chạy thật một lần**: mở trình duyệt vào trang vừa làm, xem log backend
  không có 404/422 phát sinh. SSR trả 200 **kể cả khi** lời gọi bên trong
  hỏng — mã trạng thái của trang không phải bằng chứng.

---

## 3. Hợp đồng API

Mọi endpoint dưới đây **đã tồn tại và đã chạy**. Không sửa backend.

Nhóm `/api/v1/user/*` đòi `Authorization: Bearer <JWT>`; `AuthInterceptor` đã
tự gắn.

| endpoint | method | body / params | trả về |
|---|---|---|---|
| `/api/v1/user/follows` | POST | `{target_type, target_id}` | `{status: "ok", followed: "<chuỗi>"}` |
| `/api/v1/user/follows` | GET | — | `{follows[], total}` |
| `/api/v1/user/follows/{follow_id}` | DELETE | — | `{status: "ok"}` |

**`followed` là một CHUỖI, không phải boolean.** Backend trả
`str(follow.target_id)` — xem `app/api/user.py::follow_target`. Bản lượt 2 khai
`followed: boolean` trong `user.service.ts`; sai, và sai theo kiểu không gây
lỗi ngay: chuỗi khác rỗng là truthy nên `if (res.followed)` vẫn chạy đúng,
chỉ `res.followed === true` mới hỏng. §4.2 sửa chỗ này.

Chi tiết các kiểu hay sai:

- `target_type` là `Literal["game","series","developer","streamer"]`. Giá trị
  khác → **422**.
- `target_id` của **game** là ObjectId dạng chuỗi. Của **series / developer /
  streamer** là slug hoặc tên, giữ nguyên chuỗi. Backend tự phân biệt theo
  `target_type` — xem chú thích trong `follow_target`.
- Khoá upsert là `{user_id, target_type, target_id}`. Theo dõi cùng một studio
  hai lần là vô hại, không tạo bản ghi thứ hai.
- `POST /follows` **không trả `_id`**. Muốn xoá phải `GET /follows` đọc lại lấy
  `id`. `game.component.ts::doiTheoDoi` đã làm đúng việc này, xem lại chỗ đó.
- `follows[]`: `{id, target_type, target_id, target}`. `target` là `null` với
  **mọi mục không phải game** — bình thường, không phải lỗi tải. Trang
  `/follows` đã xử lý đúng rồi, đừng đụng vào.
- **Không gửi `user_id`** trong bất kỳ body nào.

---

## 4. Hạng mục

Làm theo thứ tự. Mỗi mục một commit.

### 4.1 `/thu-vien` không có trong nav — **làm trước, nhỏ nhất**

**Vấn đề:** trang thư viện dựng ở lượt 2 chỉ tới được qua một thẻ ở `/profile`.
Nó không nằm trong `nav.component.ts::mucCaNhan`, nên không gõ tay URL thì
phần lớn người dùng không biết nó tồn tại.

Đây là **lần thứ ba** repo mắc đúng lỗi này. Chú thích ngay phía trên
`mucCaNhan` đã ghi hai lần trước:

> *"Trước đây chúng không nằm trong nav nào — không gõ tay URL thì không tới
> được, đúng lỗi mà `/free` đã mắc ở lượt 10."*

**Việc:** thêm `{ duongDan: '/thu-vien', nhan: 'Thư viện' }` vào `mucCaNhan`.

**Đọc kỹ chỗ này trước khi viết "xong":** `mucCaNhan` **chỉ được render trong
menu mobile** — khối `*ngIf="dangMoMobile"` ở `nav.component.html:77`, mang
class `md:hidden`. Bản desktop không có mục cá nhân nào; ba trang
`/canh-bao-gia`, `/follows`, `/wrapped` trên desktop cũng chỉ tới được qua
`/profile`. Nên:

- Thêm vào `mucCaNhan` sửa được **bản mobile**. Đó là toàn bộ phạm vi mục này.
- Trên desktop, `/thu-vien` đã có thẻ dẫn ở `/profile` từ lượt 2 — đủ, ngang
  bằng ba trang kia.
- **Đừng tự dựng menu cá nhân cho desktop.** Đó là một quyết định thiết kế,
  không phải một chỗ còn thiếu; xem §5.

**Xong khi:** đăng nhập → mở menu mobile → thấy "Thư viện" → bấm vào ra đúng
trang.

**Test:** `app.component.spec.ts` đã có ca chốt nav trỏ tới ba trang công khai.
Thêm ca cho nhóm cá nhân — `mucCaNhan` chỉ hiện khi đã đăng nhập **và** menu
mobile đang mở, nên phải stub `AuthService` rồi gọi `doiMenuMobile()`. Dùng
`duongDanCoThat()` chốt mọi href trong nav là route thật; làm vậy thì lần thứ
tư không xảy ra được nữa.

### 4.2 `followed` khai sai kiểu

**Vấn đề:** `user.service.ts::follow` khai
`Observable<{ status: string, followed: boolean }>`. Backend trả
`{"status": "ok", "followed": str(target_id)}` — `followed` là chuỗi.

Hiện chưa gây lỗi vì `doiTheoDoi()` bỏ qua phản hồi và gọi lại `GET /follows`.
Nhưng đây đúng là hạng lỗi đã làm hỏng phần huy hiệu, chỉ là chưa ai chạm tới.

**Việc:** sửa kiểu cho đúng. Kèm chú thích nói rõ `followed` là `target_id`
chứ không phải cờ bật/tắt — cái tên gợi ý sai, và đó là lý do nó bị đoán nhầm.

**Test:** `api-paths.spec.ts` đã có ca cho `follow`. Thêm khẳng định về hình
dạng phản hồi.

### 4.3 Theo dõi series và studio — **hạng mục chính**

**Vấn đề:** backend nhận cả 4 `target_type`, trang `/follows` đã render đủ 4
nhãn (`nhanLoai()` có sẵn `Series`, `Studio`, `Streamer`). Nhưng **chỉ game
mới theo dõi được** — nút ở trang game gửi cứng `'game'`. Ba loại kia là mã
chết: không có đường nào tạo ra một mục để mà hiện.

**Việc:** ở `web/src/app/pages/game/`, thêm nút theo dõi cho:

- **Series** — `GameDetail.series` (`string | null`). Không có thì không hiện
  nút, đừng hiện nút chết.
- **Studio** — `GameDetail.developers` (`string[]`). Nhiều studio thì mỗi cái
  một nút; mảng rỗng thì không hiện gì.

Cả hai gửi `target_id` là chính chuỗi ấy, không encode, không đổi hoa thường —
backend lưu nguyên văn và `follows_of` tra lại đúng chuỗi đó.

**Cạm bẫy:**

- `napTheoDoi()` hiện tìm theo `f.target_type === 'game' && f.target_id ===
  gameId`. Nay phải tra được nhiều mục cùng lúc. Đừng gọi `GET /follows` một
  lần cho mỗi nút — một lần đọc, rồi đối chiếu trong bộ nhớ.
- Trạng thái "đang bận" phải **theo từng nút**. Một cờ `dangDoiTheoDoi` dùng
  chung sẽ khoá cả cụm khi người dùng bấm một nút, và với game có bốn studio
  thì điều đó rất rõ.
- `target` của series/studio là `null` ở `/follows` — **đúng như thiết kế**.
  Trang đó hiển thị bằng `target_id` trần. Đừng "sửa" nó thành trạng thái lỗi.

**Xong khi:** theo dõi một studio từ trang game → mục hiện ở `/follows` với
nhãn "Studio" và tên studio → bỏ theo dõi được từ cả hai nơi → mở lại trang
game thì nút vẫn ở trạng thái đã theo dõi.

### 4.4 Dọn nợ lượt 2

Bốn việc nhỏ, gộp được vào một commit.

- **`news.component.ts` rò subscription.** `searchSubject.pipe(...).subscribe()`
  trong `ngOnInit` không có `OnDestroy` tương ứng.
- **`community.service.ts::getScore()` là mã chết.** Không ai gọi — trang game
  đọc `community_score` nhúng sẵn trong `GameDetail`. Xoá, hoặc nếu giữ thì
  ghi rõ vì sao giữ.
- **Lối đặt tên thứ ba.** `reviewScore`, `reviewComment`, `selectedGameId`,
  `searchResults`, `hienDropdown` trộn lẫn với `dangTai`, `napCanhBao`,
  `dongBoKetQua`. `CLAUDE.md` và `HANDOFF-2.md` §6 đều nói tiếng Việt không
  dấu. Đổi cho thống nhất.
- **Liên kết đăng nhập ở trang game chưa có test.** Nó nằm trong
  `*ngIf="game as g"` nên muốn render phải dựng một `GameDetail` đầy đủ cùng
  sáu service. Dựng một fixture tối thiểu dùng lại được, rồi chốt bằng
  `duongDanCoThat()`.

---

## 5. Việc KHÔNG giao — và vì sao

| mục | lý do |
|---|---|
| Banner khuyến mãi | `app/services/promotions.py` vẫn **chỉ có hàm đọc**, không writer nào. Đã kiểm lại lượt 15: không đổi. Dựng giao diện cho dữ liệu vĩnh viễn rỗng thì không nghiệm thu được. |
| Giftcode | Y hệt. |
| `POST /library/epic/bulk` | Vẫn trả **501** có chủ đích. Cần job catalog Epic đánh dấu game từng free theo tuần trước đã. |
| Tên người viết đánh giá | `/community/games/{id}/reviews` trả `user_id` trần vì `users` **chưa lưu tên hiển thị**. Muốn hiện tên thì phải sửa backend — ngoài phạm vi. Để nguyên `user_id`, đừng bịa tên. |
| Theo dõi streamer | `target_type: "streamer"` chạy được, nhưng chưa có trang streamer nào để đặt nút, và mảng Twitch của Phase 7 vẫn đang bị chặn (2FA). Cần quyết định trước. |
| Menu cá nhân cho desktop | Bản desktop hiện không có mục cá nhân nào trong nav — cả bốn trang đòi đăng nhập đều chỉ tới được qua `/profile`. Đó có thể là cố ý (giữ nav gọn) hoặc là chỗ còn thiếu, và chỉ chủ dự án trả lời được. Đừng tự dựng. |
| Thông báo đẩy | Đang chờ 5 giá trị Firebase. Không đụng. |
| Sửa backend | Ngoài phạm vi. Thiếu gì thì hỏi. |

---

## 6. Quy ước repo

Giữ nguyên `HANDOFF-2.md` §6. Nhắc lại ba điều bị vi phạm ở lượt 2:

- Tên biến/hàm mới **tiếng Việt không dấu** (`dangTai`, `napCanhBao`,
  `moTaDieuKien`). Đừng thêm lối đặt tên thứ ba.
- Chú thích giải thích **vì sao**, không phải *cái gì*. Chỗ nào từng sai thì
  ghi lại cái sai đó — đó là lệ của repo này.
- Mỗi hạng mục một commit, message tiếng Việt.

Thêm cho lượt này:

- Liên kết nội bộ mới → chốt bằng `routes.spec-util.ts::duongDanCoThat()`.
- Interface mới cho phản hồi API → trong spec phải có một hằng số chép **đúng
  JSON thật** endpoint trả về, kèm chú thích "sửa interface, đừng sửa hằng số
  này nếu nó đỏ". Xem `user-profile.component.spec.ts::BADGES_THAT` làm mẫu.
- Không gọi hàm trong `*ngFor` — dựng sẵn mảng trong component.
