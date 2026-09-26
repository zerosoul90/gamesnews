# PHASE 9 — Lấp khoảng trống, mở rộng mũi nhọn giá, ra mắt

## Trước khi bắt đầu

Đọc `CLAUDE.md`, `PLAN.md`, `PROGRESS.md` (lượt 29 — bảng rà soát).

Phase 0-8 đều có mặt trong code, nhưng rà ngày 2026-09-26 cho thấy nhiều
checkpoint chưa đạt và vài mục đánh dấu xong mà chưa làm (xem bảng ở
`PROGRESS.md` lượt 29). Phase này không mở hướng sản phẩm mới: nó làm cho mũi
nhọn đã chốt — **giá VND kèm đáy lịch sử** — dùng được thật, rồi đưa ra mắt.

## Mục tiêu

Bốn đợt, theo thứ tự. Mỗi đợt kết thúc bằng checkpoint riêng.

| Đợt | Nội dung | Vì sao ở vị trí này |
|---|---|---|
| A | Lấp khoảng trống rẻ | Dữ liệu đã có, chỉ thiếu lớp hiển thị |
| B | Tính năng giá mới | Mũi nhọn đã chốt |
| C | Trang SEO theo mùa | Có hạn chót: đợt sale lớn cuối năm của Steam |
| D | Ra mắt | Chuẩn bị song song với A-C; phần tài khoản/khoá là việc của người dùng |

## Dữ liệu hiện có (đo 2026-09-26)

Các con số này quyết định cái gì làm được ngay và cái gì phải chờ:

- `price_history` bắt đầu từ **2026-09-09**; 31.122 / 34.656 game mới có
  **một** bản ghi. Mọi tính năng cần "chu kỳ giảm giá" của chính mình đều chưa
  đủ dữ liệu — phải chờ tích luỹ, hoặc dùng nguồn ngoài.
- `price_intl` (CheapShark, USD): **1.854** game.
- `game_hotness`: **59** game, 50 có CCU, 23 có momentum dương.
- `games`: 43.909, có `genres` gần hết, **không có tag**.
- `user_library`: nhập wishlist **chưa được làm** (`services/user_library.py`
  có dòng "Chưa xử lý wishlist ở đây").

## Đợt A — Lấp khoảng trống rẻ

### A1. Bảng "Phổ biến nhất" / "Đang tăng mạnh" — đã làm (lượt 30), chờ dữ liệu cho checkpoint

Job tính `game_hotness` đã chạy từ Phase 7 mà không có API, không có trang.

- API `GET /api/v1/hot?board=popular|rising`, trang `/hot`, khối nhỏ ở `/`
- **Mở rộng tập theo dõi** từ 59 lên vài trăm game (ưu tiên game có giá VN và
  nhiều review). Với 59 game, "Đang tăng mạnh" gần như rỗng
- Bảng "Đang tăng mạnh" xếp theo `score_momentum`, loại game top thường trực

**Checkpoint (của Phase 7):** "Đang tăng mạnh" không bị CS2/Dota 2 chiếm chỗ;
bảng có ≥ 20 game.

### A2. Route i18n + `hreflang`

`PLAN.md` đòi dựng từ Phase 4 "để thêm ngôn ngữ sau không phải đổi cấu trúc
URL". Chưa làm, nhưng **rẻ hơn tưởng**: nếu chốt tiếng Việt ở gốc (URL hiện
tại giữ nguyên) và tiếng Anh dưới `/en/`, thì không URL nào phải đổi.

- Chốt quy ước URL trên, ghi vào `PLAN.md`
- `<html lang="vi">`, `hreflang="vi"` + `x-default` trên mọi trang, sitemap có
  `xhtml:link`
- Nội dung tiếng Anh **để sau** — chỉ dựng khung

**Checkpoint:** mọi trang SSR có `hreflang` đúng; không URL nào đổi.

## Đợt B — Tính năng giá mới

### B1. Nhập wishlist Steam + trang "Wishlist đang giảm giá"

- Làm nốt nhập wishlist (`IWishlistService/GetWishlist`, profile public — cùng
  đường lỗi `PROFILE_IS_PRIVATE` đã có)
- Trang cá nhân: game trong wishlist đang giảm, xếp theo mức giảm và độ gần
  đáy lịch sử
- Tự tạo cảnh báo `historical_low` cho game trong wishlist (người dùng tắt được)

Không phụ thuộc FCM: trang web dùng được ngay cả khi push chưa chạy.

**Checkpoint:** tài khoản thật có wishlist public → trang hiện đúng các game
đang giảm, đối chiếu tay với Steam.

### B2. So giá Việt Nam với quốc tế

- Trên trang game: "Giá Steam VN rẻ hơn Mỹ X%" khi có cả hai giá
- Trang tổng hợp: game rẻ ở VN nhất so với quốc tế
- Mở rộng độ phủ `price_intl` (1.854 game) — ưu tiên game có giá VN

So hai tiền tệ cần tỉ giá. **Không cắm tỉ giá vào mã nguồn** (lý do đã ghi ở
`services/intl_prices.py`); cần một nguồn tỉ giá miễn phí — kiểm hạn mức và
điều khoản trước khi dùng.

### B3. "Nên mua hay chờ" — bản không cần lịch sử dài

Lịch sử của chính mình chưa đủ (mới 2,5 tuần). Bản đầu dựa vào thứ đã có:
đáy lịch sử (`lowest_ever`, mức giảm sâu nhất từ CheapShark) và khoảng cách
tới đợt sale lớn kế tiếp (lịch ở C1). Bản dựa trên chu kỳ giảm giá của từng game
để sau khi có ≥ 1 năm dữ liệu.

## Đợt C — Trang SEO theo mùa

### C1. Lịch Steam Sale + đếm ngược

- Lịch các đợt sale lớn (Mùa thu, Mùa đông, Tết Âm lịch, Mùa hè...) —
  curate tay theo năm, **đối chiếu với lịch Valve công bố** trước khi đăng
- Trang mỗi đợt: đếm ngược, và khi đang diễn ra thì các game giảm sâu nhất /
  chạm đáy lịch sử
- Dùng cho B3

**Hạn chót:** sale mùa thu của Steam thường rơi vào cuối tháng 11. Trang phải
lên và được index **trước** đợt đó, không phải trong đợt.

### C2. Game tương tự

`genres` của Steam quá thô ("Action", "Indie") để gợi ý. Vector Qdrant hiện chỉ
chứa **tên** game — lượt 28 đo được hai phần của một series giống nhau tới 0.97
— nên cũng không dùng được.

Cần tag của người dùng Steam. Ứng viên: SteamSpy (miễn phí, có tag theo appid).
**Phải kiểm hạn mức và điều khoản trước**, rồi ghi vào `DATA-SOURCES.md`. Có
tag thì so trùng tag + genre, không cần embedding.

### C3. Lịch sử game miễn phí trên Epic — hoãn

`freeGamesPromotions` chỉ trả tuần này và tuần sau; lịch sử phải tự tích luỹ
từ bây giờ. Làm khi đã có vài tháng dữ liệu.

## Đợt D — Ra mắt

Chuẩn bị song song với A-C.

**Phần tôi làm:**

- `docker-compose.prod.yml`: image chạy được trên ARM64 (Oracle Always Free là
  ARM), HTTPS, không lộ cổng kho dữ liệu, sao lưu Mongo định kỳ
- Checklist triển khai từng bước, kiểm được sau mỗi bước
- Nối FCM thật khi có khoá — chặng cuối của mọi thông báo đẩy

**Phần của người dùng:** tài khoản Oracle Cloud, domain, project Firebase,
Google Search Console.

**Checkpoint:** site chạy trên domain thật qua HTTPS; `/health` xanh; một push
thật đến được máy.

## Không làm trong phase này

- Mobile: app Flutter mới là khung (454 dòng), và máy dev không đủ Dart để
  kiểm. Làm sau khi web đã ra mắt.
- Giftcode: có endpoint nhưng không có nguồn dữ liệu. Cần chốt nguồn trước.
- Streamer/Twitch: vẫn bị chặn vì 2FA bằng số điện thoại.
