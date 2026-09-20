# Bàn giao lượt 4 — bộ lọc tìm kiếm, và dọn nốt nợ đổi tên

Tài liệu giao việc cho agent ngoài (antigravity). Người viết sẽ **review lại
toàn bộ code** trước khi merge.

Đọc kèm: `CLAUDE.md`, `HANDOFF-3.md` (§1 và §2 vẫn còn hiệu lực nguyên vẹn),
`PROGRESS.md` lượt 16.

---

## 0. Lượt 3 làm được gì, và hỏng ở đâu

**Phần làm tốt, giữ nguyên cách làm:** bốn commit, mỗi hạng mục một cái.
Không endpoint bịa. Test nav duyệt **mọi** `a[href]` qua `duongDanCoThat()`
chứ không chốt riêng một liên kết — đó là hình mẫu đúng của một guard, và lỗi
"trang không có trong nav" nay không tái diễn được. Cạm bẫy §4.3 xử lý đúng
hết: trạng thái bận theo từng nút, một lần `GET /follows` cho cả trang.

**Nhưng nút "theo dõi Series" là mã chết ngay từ lúc giao.** `games.series`
null trên cả 38.721 document (số đo lúc review lượt 3; catalog nay đã 39.284
và vẫn 0); không job nào ghi vào nó. `*ngIf="g.series"` không bao giờ đúng.

**Lỗi đó thuộc về tài liệu này, không thuộc về người làm.** `HANDOFF-3.md`
§4.3 giao việc ấy sau khi tôi xác nhận `GameDetail.series` có trong interface
và backend map nó ra. Tôi kiểm **khai báo kiểu**, không kiểm **dữ liệu**.

> Trường có trong schema, có trong OpenAPI, có trong TypeScript interface —
> vẫn có thể rỗng 100%.

Nên lượt này mọi hạng mục dưới đây đều **đã được đếm trên catalog thật**, và
số đo nằm ngay trong phần mô tả. Một hạng mục bị loại (§4.2) chính vì phép đếm
ấy. Nếu bạn thấy một chỗ "đáng lẽ nên làm" mà §4 không nhắc — nhiều khả năng
nó đã bị đếm và loại; hỏi trước khi tự thêm.

**Hai món nữa lọt lưới, cùng một hình dạng:**

1. **Hạng mục chính không có test nào.** `65d8c80` đổi 76 dòng, 0 spec. Số
   test web đi 45 → 47 và cả hai ca mới đều thuộc hạng mục khác.
2. **Đổi tên nửa chừng.** `news.component.ts` giờ trộn `ketQuaTimKiem` với
   `searchQuery`/`searchSubject`; `game.component.ts` trộn `diemDanhGia` với
   `dangGuiReview`/`reviewsTotal` — **trong cùng một khối khai báo**. Trước khi
   sửa nó ít ra còn nhất quán. Xem §6.

---

## 1. Bốn điều tuyệt đối không làm

Giữ nguyên từ `HANDOFF-3.md` §1: **không bịa endpoint**, **không mock**,
**không nói sai trên giao diện**, **không khai một trường chưa nhìn thấy trong
phản hồi thật**.

Lượt này thêm điều thứ năm:

**5. Không dựng giao diện cho dữ liệu mà bạn chưa đếm.** Trước khi làm một ô
lọc, một thẻ, một biểu đồ — đếm xem trường nó đọc có bao nhiêu giá trị thật:

```bash
docker exec gamesnews-mongo-1 mongosh --quiet --eval '
  db = db.getSiblingDB("gamesnews");
  print(db.games.countDocuments({truong: {$ne: null}}));
  print(JSON.stringify(db.games.distinct("truong").slice(0, 20)));'
```

Ra 0, hoặc ra một giá trị duy nhất chiếm 99,99% — thì dừng và hỏi.

---

## 2. Cổng nghiệm thu

| cổng | lệnh |
|---|---|
| web build | `cd web && npm run build` |
| web test | `cd web && npx ng test --watch=false --browsers=ChromeHeadlessNoSandbox` |
| python | `uv run ruff check . && uv run mypy app tests && uv run pytest` |
| mobile | `cd mobile && flutter analyze` |

**Cổng `python` gồm ba lệnh, không phải hai.** Tôi từng báo cổng ấy xanh khi
mới chạy `ruff` + `mypy`, và một test đỏ nằm im vì thế.

**Chạy từ đúng thư mục, và in mã thoát.** Trong phiên review lượt 3 tôi dính
hai lần: `ng test` chạy từ gốc repo trả về **không một dòng nào** (grep nuốt
mất `npm error`), và `mypy` chạy từ `web/` báo "Found 1 error". Kết thúc mọi
lệnh cổng bằng `; echo "EXIT=$?"`.

Mỗi hạng mục phải:

- **Một hạng mục, một commit.** Message tiếng Việt, nói **vì sao**. Lượt 3
  viết message một dòng tả *cái gì* — đọc lại `git log` sau ba tháng thì phần
  đó vô dụng.
- **Có test đi kèm, và test ấy phải đỏ khi gỡ bản sửa ra.** Cách kiểm: sửa
  ngược về bản sai, chạy test, xem thông báo đỏ có đúng triệu chứng không, rồi
  revert. Ghi bảng "gỡ ra → đỏ với" vào commit message; xem `70cdd7a` và
  `aae061e` làm mẫu.
- **Đừng viết test vòng lặp kín.** Ca liên kết ở `game.component.spec.ts` bản
  lượt 3 chọn phần tử bằng `a[routerLink="/login"]` rồi khẳng định chính giá
  trị vừa dùng để chọn là route thật. Nó đỏ khi revert nên qua cổng, nhưng
  không bắt được liên kết hỏng nào **khác**. Bản đã sửa duyệt hết
  `a[href^="/"]` — làm theo bản đó.
- **Chạy thật một lần**: mở trình duyệt vào trang vừa làm, xem log backend
  không có 404/422 phát sinh.

---

## 3. Hợp đồng API — `GET /search`

Endpoint đã tồn tại và đã chạy. Không sửa backend.

| tham số | kiểu | mặc định | ghi chú |
|---|---|---|---|
| `q` | string | `""` | **được phép rỗng** — lọc không cần từ khoá |
| `platform` | string | — | slug thường, xem §4.1 |
| `genre` | string | — | slug thường, xem §4.1 |
| `year` | int | — | năm phát hành |
| `type` | string | — | **đừng dùng**, xem §4.2 |
| `page` | int | 1 | |
| `per_page` | int | 20 | |

Phản hồi: `{query, total, page, per_page, hits[]}`. `hits[]` là
`{id, slug, titles{primary,vi,ja}, platforms[], genres[], type, release_year, cover}` —
đúng như `SearchHit` trong `search.service.ts` đang khai, không cần đổi.

Đã đo trên API thật:

```
q=elden                  -> total 59
q=elden&platform=pc      -> total 59
q=elden&platform=switch  -> total 0
q=&genre=rpg             -> total 1000
q=&genre=khong-co-that   -> total 0      <- sai giá trị thì trả rỗng, không trả hết
q=&year=2024             -> total 353
```

**`total` bị chặn ở 1000.** Đó là `maxTotalHits` mặc định của Meilisearch,
không phải lỗi: `genre=rpg` thật ra có **6.660** game trong Mongo. Hệ quả:

- `page=50` là trang cuối còn kết quả; `page=51` trở đi trả về **0 hit** nhưng
  `total` vẫn là 1000.
- Điều kiện phân trang hiện có (`page * limit < response.total`) đúng **tình
  cờ**: ở trang 50 thì `50*20 = 1000`, không nhỏ hơn 1000, nên nút "sau" tự ẩn.
  **Đừng "sửa" nó.**
- Nhưng con số hiển thị thì đang nói sai. Khi `total === 1000`, hiện
  **"1000+"** thay vì "1000" — xem `HANDOFF-3.md` §1 điều 3.

---

## 4. Hạng mục

Làm theo thứ tự. Mỗi mục một commit.

### 4.1 Bộ lọc cho trang tìm kiếm — **hạng mục chính**

**Vấn đề:** `/search` nhận bốn bộ lọc, `search.service.ts` chỉ gửi `q`, `page`,
`limit`. Toàn bộ khả năng lọc chưa có đường nào tới được từ giao diện.

**Việc:** thêm ba ô lọc ở `web/src/app/pages/search/`. Đã đếm trên catalog:

| lọc | phủ | số giá trị | giá trị |
|---|---|---|---|
| `platform` | 39.284/39.284 (100%) | 8 | `android` `ios` `pc` `ps4` `ps5` `switch` `xbox-one` `xbox-series` |
| `genre` | 39.169/39.284 (99,7%) | 59 | `indie` (27.255), `action` (17.303), `adventure` (15.186), `casual` (14.700), `strategy` (8.120), `simulation` (8.100), `rpg` (6.660), `early-access` (3.168)… |
| `year` | 37.239/39.284 (94,8%) | — | từ `release_dates` |

Giá trị gửi lên là **slug thường, nguyên văn** như trên — không viết hoa,
không dịch. Nhãn tiếng Việt thì hiển thị ở giao diện, đừng gửi lên API.

59 genre là quá nhiều cho một hàng nút. Chọn cách hiển thị bạn thấy hợp (ô
`select`, hoặc vài genre đầu + "xem thêm") — nhưng **đừng viết cứng danh sách
tám genre ở trên**: đó là top 8 lúc viết tài liệu, không phải toàn bộ.

**Cạm bẫy — đọc hết trước khi viết:**

1. **`doSearch()` đang bỏ chạy khi `q` rỗng** (`if (!this.query.trim()) return`).
   Backend cho lọc không cần từ khoá — đã đo `q=&genre=rpg` ra 1000 kết quả.
   Giữ nguyên guard ấy thì người dùng chọn genre xong nhìn thấy trang trắng.
   Điều kiện đúng là: không có `q` **và** không có bộ lọc nào.
2. **Link phân trang đang dựng lại `queryParams` chỉ với `{ q, page }`**
   (`search.component.html` dòng 59 và 66). Thêm lọc mà quên chỗ này thì bấm
   sang trang 2 là mất sạch bộ lọc — lỗi chỉ lộ ra ở trang thứ hai.
3. **Bộ lọc phải nằm trong URL**, cùng cách `q` và `page` đang làm. Trang này
   đọc trạng thái từ `route.queryParams`, nên lọc mà giữ trong biến component
   sẽ không sống qua F5, không chia sẻ được link, và SSR dựng ra một trang
   khác với trang người dùng thấy.
4. **Đổi bộ lọc phải đưa `page` về 1.** Đang ở trang 7 của "indie" rồi lọc
   sang một genre chỉ có 12 kết quả thì trang 7 là rỗng.

**Xong khi:** chọn platform + genre không cần gõ từ khoá vẫn ra kết quả → F5
giữ nguyên bộ lọc → sang trang 2 vẫn giữ → đổi genre thì về trang 1 → log
backend không có 422 nào.

### 4.2 KHÔNG làm bộ lọc `type`

Endpoint có nhận `type`, và sẽ rất hợp lý nếu chỉ nhìn OpenAPI. Nhưng:

```
type game = 39282
type dlc  = 1
type demo = 1
```

Một ô lọc mà một lựa chọn trả về gần như toàn bộ catalog còn hai lựa chọn kia
trả về đúng một game mỗi cái thì không phải bộ lọc. Đây chính là phép đếm đã
cứu lượt này khỏi lặp lại ca `series`.

**Việc thật sự cần làm ở đây, ngược lại:** thẻ kết quả đang in
`{{ hit.type }}` viết hoa (`search.component.html` dòng 50), nên **mọi** thẻ
đều hiện chữ "GAME". Gỡ nó đi — một nhãn giống hệt nhau trên mọi kết quả
không mang thông tin nào, chỉ chiếm chỗ.

Gộp chung một commit với §4.1 cũng được, nhưng chú thích phải ghi lại con số
trên để lần sau không ai dựng lại.

### 4.3 Dọn nốt nợ đổi tên

Lượt 3 đổi tên được một nửa rồi dừng, để lại hai file trộn hai lối đặt tên
trong cùng một khối khai báo:

- `news.component.ts`: `ketQuaTimKiem`, `hienDanhSach`, `idGameChon`,
  `tenGameChon` đứng cạnh `searchQuery`, `searchSubject`, `searchSub`,
  `onSearchChange`.
- `game.component.ts`: `diemDanhGia`, `binhLuan` đứng cạnh `dangGuiReview`,
  `loiReview`, `reviewsTotal`.

Đổi nốt cho thống nhất, **cả template** (`[(ngModel)]`, `(ngModelChange)`).

Kèm một món nhỏ: `CommunityScore` trong `community.service.ts` thành mã chết
từ khi `getScore()` bị xoá ở lượt 3 — `game.service.ts` có bản riêng và mọi
chỗ dùng đều trỏ vào bản ấy. Xoá đi.

**Lưu ý phạm vi:** `search.component.ts` (file bạn sửa ở §4.1) đang **nhất
quán tiếng Anh** — `query`, `page`, `limit`, `isLoading`, `doSearch`. Nó có
trước lệ tiếng Việt. Đặt tên mới trong file ấy theo đúng lối đang có ở đó, và
**đừng đổi tên nửa vời** — nếu định chuyển cả file sang tiếng Việt thì làm
trọn trong một commit riêng, còn không thì để nguyên. Nửa vời là tệ nhất
trong ba lựa chọn.

---

## 5. Việc KHÔNG giao — và vì sao

| mục | lý do |
|---|---|
| Bộ lọc `type` | 39.282 / 1 / 1. Xem §4.2. |
| Theo dõi series | `games.series` null trên cả 39.284 document, không writer nào. Việc đầu tiên nằm ở backend. |
| **Trang "game đang hot"** | `game_hotness` có **58 bản ghi thật**, cron `job_compute_hotness` chạy mỗi giờ, service `hotness_of` đã viết — nhưng **không endpoint nào** trong `app/api/` đọc nó. Dữ liệu sống mà không có đường ra. Cần một endpoint trước; đó là việc backend và là hạng mục riêng. |
| Banner, giftcode | `app/services/promotions.py` vẫn chỉ có hàm đọc, không writer. Đã kiểm lại lượt 16. |
| `POST /library/epic/bulk` | Vẫn 501 có chủ đích. |
| Tên người viết đánh giá | `users` chưa lưu tên hiển thị. Để nguyên `user_id`, đừng bịa tên. |
| Theo dõi streamer | Chưa có trang streamer, và mảng Twitch của Phase 7 còn bị chặn (2FA). |
| Menu cá nhân cho desktop | Quyết định thiết kế, chưa chốt. Xem `HANDOFF-3.md` §5. |
| Sửa backend | Ngoài phạm vi. Thiếu gì thì hỏi. |

---

## 6. Quy ước repo

Giữ nguyên `HANDOFF-3.md` §6. Nhấn lại ba điều lượt 3 làm chưa tới:

- **Đổi tên thì đổi trọn.** Nửa vời để lại hai lối đặt tên trong cùng một khối
  khai báo, tệ hơn cả không đổi. Nếu một file đang nhất quán theo lối cũ, theo
  lối cũ trong file ấy — hoặc chuyển cả file trong một commit riêng.
- **Liên kết nội bộ mới** → chốt bằng `routes.spec-util.ts::duongDanCoThat()`,
  duyệt hết `a[href^="/"]` chứ không chọn sẵn một cái.
- **Interface mới cho phản hồi API** → trong spec phải có hằng số chép đúng
  JSON thật, kèm chú thích "sửa interface, đừng sửa hằng số này nếu nó đỏ".
  Xem `user-profile.component.spec.ts::BADGES_THAT`.

Và một điều mới, rút từ chính lượt 3:

- **Cần chọn phần tử trong test thì thêm `data-*`**, đừng chọn theo nội dung
  chữ. Cụm nút theo dõi có nhiều nút cùng mang chữ "Theo dõi"; `data-theo-doi`
  phân biệt được, chuỗi "Theo dõi" thì không. Xem `game.component.html`.
