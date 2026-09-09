# DATA-SOURCES.md — Nguồn dữ liệu

Nguyên tắc: **chỉ dùng nguồn miễn phí**. Mỗi nguồn phải nằm sau một adapter
thay thế được.

## 1. Dùng được — miễn phí, không vướng điều khoản

### Catalog

| Nguồn | Endpoint / cách dùng | Auth | Giới hạn |
|---|---|---|---|
| Steam app list | `IStoreService/GetAppList/v1` | **Steam Web API key** | 100k lượt/ngày mỗi key |
| Steam chi tiết app | `store.steampowered.com/api/appdetails` | không | ~200 req/5 phút mỗi IP |
| App Store | `itunes.apple.com/search` + `/lookup` + RSS `genre=6014` | không | ~20 req/phút |
| Google Play | thư viện `google-play-scraper` | không | dễ vỡ, cần giám sát |
| ~~IGDB~~ | ~~API IGDB qua tài khoản Twitch developer~~ | **không lấy được key** | — |

**Steam là xương sống catalog** (đổi từ IGDB, 2026-09-08). Console developer
của Twitch bắt buộc bật 2FA bằng số điện thoại; tài khoản không làm được nên
IGDB mất hẳn. Steam phủ PC dày hơn IGDB — `include_games=true` cho 184.981
game — nhưng mất hai thứ IGDB có: alternative names (nguồn alias đã tính
trước) và ngày phát hành theo từng region/platform.

Điểm yếu chung với IGDB: phủ mobile/gacha kém → bù bằng hai store mobile.
Đây lại đúng là mảng quan trọng nhất với thị trường VN.

Ba chốt đã kiểm bằng tay ngày 2026-09-08, ghi lại vì tài liệu trên mạng còn
đầy hướng dẫn cũ:

- `ISteamApps/GetAppList` **đã bị Valve gỡ** — trả "Method 'GetAppList' not
  found in interface 'ISteamApps'". Trong 27 interface không cần key cũng
  không còn method nào liệt kê app. Muốn danh sách app thì bắt buộc có key.
- `appdetails` trả `success: false` kèm **HTTP 200** cho app đã gỡ, app không
  bán ở VN, hoặc khi bị bóp tốc độ. Đây không phải lỗi.
- App Store: API marketing v2 của Apple chỉ có bảng "apps" và bảng đó **loại
  hẳn game**. Bảng xếp hạng game chỉ lấy được qua endpoint RSS đời cũ có
  `genre=6014`.

### Giá & Deal

| Nguồn | Endpoint | Auth | Giới hạn |
|---|---|---|---|
| Steam | `store.steampowered.com/api/appdetails?appids={id1},{id2}&cc=vn&filters=price_overview` | không | **~200 req/5 phút mỗi IP; tối đa 50 appid + 1 quốc gia mỗi request** (đo ngày 2026-09-08) |
| Epic (free games) | `store-site-backend-static-ipv4.ak.epicgames.com/freeGamesPromotions` | không | ổn định, REST |
| Epic (catalog/giá) | `www.epicgames.com/graphql` → `Catalog.searchStore`, có `promotions` / `upcomingPromotionalOffers` | không | có bot protection, thỉnh thoảng 403 |
| CheapShark | API công khai, 35+ store PC | không | miễn phí hoàn toàn |

**Ràng buộc quan trọng nhất của cả hệ thống** là giới hạn 200 req/5 phút của
Steam, nhưng với 50 appid mỗi request, ta có thể quét tới 10.000 game/5 phút ≈ 2,88 triệu lượt/ngày mỗi IP (đo ngày 2026-09-08). Dư sức quét toàn bộ catalog nhiều lần một ngày, nhưng vẫn cần phân tầng tần suất để lịch sự và dành quota cho Phase 7.

Giá VND chỉ lấy được bằng `cc=vn` từ Steam. CheapShark và ITAD đều thiên về
USD/EUR. Đây chính là khác biệt của sản phẩm.

### Chỉ số hot

| Nguồn | Endpoint | Auth |
|---|---|---|
| Steam CCU | `ISteamUserStats/GetNumberOfCurrentPlayers/v1/` | Steam Web API key (miễn phí) |
| Steam most played | `ISteamChartsService/GetMostPlayedGames` | không |
| Steam top sellers / specials | `store.steampowered.com/api/featuredcategories` (lọc theo `cc`) | không |
| Steam reviews | `store.steampowered.com/appreviews/{appid}` | không |
| Twitch | Helix `Get Streams` (lọc `game_id`, `language`), `Get Top Games` | Client ID + app token |
| Twitch live push | EventSub `stream.online` / `stream.offline` | như trên, cần endpoint HTTPS công khai |
| YouTube live push | WebSub / PubSubHubbub trên feed kênh | không | **không tốn quota Data API** |

### Thư viện người dùng

| Nguồn | Endpoint | Điều kiện |
|---|---|---|
| Đăng nhập | Steam OpenID | không cần mật khẩu người dùng |
| Thư viện | `IPlayerService/GetOwnedGames/v1/` | profile "Game details" phải Public |
| Wishlist | `IWishlistService/GetWishlist/v1/` | như trên; **chỉ trả appid + priority + date_added**, phải tra ngược tên |

Endpoint cũ `store.steampowered.com/wishlist/profiles/{id}/wishlistdata/` đã bị
bỏ, đừng dùng.

### Khác

| Nguồn | Dùng cho | Ghi chú |
|---|---|---|
| Liquipedia API | Lịch esports (VCS, AoG, giải quốc tế) | CC-BY-SA, bắt buộc ghi nguồn, User-Agent riêng, giãn request |
| ProtonDB | Tương thích Steam Deck / Linux | |
| HowLongToBeat | Thời lượng chơi | không có API chính thức, thư viện cộng đồng |
| RSS các trang game | Tin tức | ưu tiên tuyệt đối so với HTML crawler |

## 2. KHÔNG dùng

### IsThereAnyDeal — vướng điều khoản, không phải phí

API key miễn phí và không có giới hạn cứng, nhưng ToS ghi rõ:

- Không được xây app **có thể bị xem là cạnh tranh** với ITAD hoặc các dự án
  của ITAD → app theo dõi giá game gần như chắc chắn rơi vào diện này
- Không được sửa đổi dữ liệu họ cung cấp, kể cả gỡ affiliate tag khỏi URL
- Họ bảo lưu quyền cắt truy cập bất cứ lúc nào không báo trước

→ Tự lấy giá thẳng từ store, dùng CheapShark làm nguồn phụ.

### SteamDB

Không có API công khai và có chính sách không cho scrape. Lấy thẳng từ endpoint
của Valve, đừng lấy qua họ.

### OpenCritic

API đi qua RapidAPI, tầng miễn phí rất hẹp, dùng thương mại phải trả tiền.
→ Thay bằng % review tích cực của Steam (miễn phí) + điểm cộng đồng tự có.

### Epic — thư viện người dùng

Không có API công khai cho bên thứ ba đọc thư viện. Epic Online Services chỉ
phục vụ nhà phát hành kiểm tra sản phẩm của chính họ. Đường không chính thức
(kiểu Legendary) đòi cầm token đăng nhập của người dùng → vi phạm ToS, rủi ro
khoá tài khoản. **Không dùng trong sản phẩm công khai.**

→ Thay bằng màn hình tick nhanh game free hàng tuần của Epic. Với đa số người
dùng Việt, thư viện Epic gần như chính là tập game free đã nhận.

### Apify và các dịch vụ scraping trả phí

Toàn bộ đều tính tiền theo kết quả. Mọi endpoint chúng bọc lại đều gọi trực
tiếp được miễn phí.

## 3. Cẩn trọng — miễn phí có điều kiện

| Nguồn | Điều kiện |
|---|---|
| YouTube Data API v3 | 10.000 units/ngày; mỗi `search` tốn 100 → chỉ ~100 truy vấn/ngày. Chỉ dùng cho nhóm hot. Live thì dùng WebSub thay thế |
| Reddit API | Tầng miễn phí cho phi thương mại. Nếu app có quảng cáo/affiliate thì thành thương mại, phải thoả thuận riêng |
| RAWG | Miễn phí phi thương mại, thương mại cần license |

→ Quyết định về affiliate ảnh hưởng trực tiếp tới ba nguồn này.

## 4. Chi phí không thể bằng 0

| Khoản | Số tiền |
|---|---|
| Apple Developer Program | 99 USD/năm — bắt buộc để lên App Store |
| Google Play Console | 25 USD một lần |
| Domain | ~250k/năm |
| Server | Oracle Cloud Always Free (4 core ARM, 24GB RAM, 200GB) — rủi ro bị thu hồi nếu nhàn rỗi, phải backup đều |

**Chi phí ẩn lớn nhất là dịch thuật, không phải server.** Cách giữ bằng 0: chỉ
dịch tiêu đề + tóm tắt 2–3 câu (giảm ~20 lần lượng token), dùng tầng miễn phí
của Gemini/Groq có kiểm soát tốc độ, hoặc self-host model nhỏ qua llama.cpp
chạy theo hàng đợi nền.

## 5. Ranh giới bản quyền

- Không tái bản nguyên văn bài viết, review hay điểm số tổng hợp của bên khác
- Lưu và hiển thị: tiêu đề + trích đoạn ngắn + link gốc + ghi nguồn, **hoặc**
  tóm tắt tự viết bằng lời mình
- Điểm phê bình phải tự tính bằng công thức trọng số của mình từ nguồn được
  phép, không lấy con số tổng hợp của Metacritic
