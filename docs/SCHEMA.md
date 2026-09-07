# SCHEMA.md — Mô hình dữ liệu

MongoDB. Phần khó nhất của toàn dự án không phải crawler mà là **entity game
chuẩn hoá**. Sai ở đây thì mọi thứ phía sau đều hỏng, và rất khó sửa về sau.

## 1. `games` — entity chuẩn

Một game = một document. Mọi thứ khác đều trỏ về đây.

```jsonc
{
  "_id": "ObjectId",
  "slug": "elden-ring",

  "titles": {
    "primary": "Elden Ring",
    "vi": "Elden Ring",
    "ja": "エルデンリング"
  },
  // Alias dùng cho entity resolution. Mỗi lần duyệt tay phải sinh thêm ở đây.
  "aliases": ["elden ring", "eldenring", "vong elden", "エルデンリング"],
  "aliases_normalized": ["elden ring", "eldenring", "vong elden"],  // bỏ dấu, lowercase

  "external_ids": {
    "igdb": 119133,
    "steam_appid": 1245620,      // khoá cầu nối tốt nhất, gần như nguồn nào cũng có
    "epic_slug": "elden-ring",
    "epic_namespace": "...",
    "gog_id": null,
    "cheapshark_id": "...",
    "google_play": null,
    "app_store": null
  },

  "type": "game",               // game | dlc | demo | bundle
  "parent_game": null,          // với DLC
  "series": "elden-ring",

  "platforms": ["pc", "ps5", "xbox-series", "android", "ios"],
  "genres": ["action-rpg"],
  "developers": ["FromSoftware"],
  "publishers": ["Bandai Namco"],

  // Ngày phát hành theo khu vực — không dùng một trường duy nhất
  "release_dates": [
    { "region": "ww", "date": "2022-02-25", "platform": "pc" }
  ],

  // Game dịch vụ dài hạn (gacha, MMO) không có "một ngày ra mắt"
  "is_live_service": false,
  "current_season": null,

  "media": { "cover": "...", "screenshots": [], "videos": [] },
  "system_requirements": { "minimum": {}, "recommended": {} },

  "region_locked_vn": false,

  "updated_at": "ISODate"
}
```

**Index bắt buộc:** `external_ids.steam_appid`, `external_ids.igdb`, `slug`,
`aliases_normalized`.

## 2. Giá

Tách hai collection. **Không lưu snapshot mỗi lần poll** — với vài chục nghìn
game sẽ ra hàng tỉ dòng vô nghĩa trong vài tháng.

### `price_current` — upsert, một dòng cho mỗi (game × store × region)

```jsonc
{
  "game_id": "ObjectId",
  "store": "steam",             // steam | epic | gog | ...
  "region": "vn",
  "currency": "VND",
  "price_initial": 1090000,
  "price_final": 436000,
  "discount_percent": 60,
  "is_free_promo": false,
  "promo_ends_at": "ISODate",

  // Tính sẵn — người mua quan tâm cái này hơn % giảm
  "lowest_ever": 327000,
  "lowest_ever_date": "ISODate",
  "is_historical_low": false,

  "url": "...",
  "checked_at": "ISODate"
}
```

Unique index: `(game_id, store, region)`.

### `price_history` — append-only, **chỉ ghi khi giá thực sự đổi**

```jsonc
{
  "game_id": "ObjectId",
  "store": "steam",
  "region": "vn",
  "price_final": 436000,
  "discount_percent": 60,
  "changed_at": "ISODate"
}
```

Index: `(game_id, store, region, changed_at)`.

## 3. `game_metrics` — time-series

MongoDB time-series collection, `timeField: ts`, `metaField: meta`.

```jsonc
{
  "ts": "ISODate",
  "meta": { "game_id": "ObjectId", "channel": "steam_ccu" },
  "value": 154320
}
```

`channel`: `steam_ccu` | `twitch_viewers` | `youtube_videos` |
`steam_reviews_new` | `vn_articles` | `internal_views` | `internal_wishlist`

**Chính sách rollup — bắt buộc, không phải tối ưu về sau:**

| Độ phân giải | Giữ |
|---|---|
| raw 15 phút | 7 ngày |
| gộp theo giờ | 90 ngày |
| gộp theo ngày (min/max/avg/peak) | vĩnh viễn |

### `game_hotness` — tính sẵn, đọc nhanh

```jsonc
{
  "game_id": "ObjectId",
  "scores": { "steam_ccu": 0.94, "twitch": 0.81, "vn_buzz": 0.62 },  // percentile 30 ngày
  "score_absolute": 0.88,       // bảng "Phổ biến nhất"
  "score_momentum": 0.31,       // bảng "Đang tăng mạnh" — delta 24h/7d
  "ccu_now": 154320,
  "ccu_peak_24h": 201005,
  "ccu_peak_all_time": 953426,
  "ccu_peak_all_time_date": "ISODate",
  "computed_at": "ISODate"
}
```

Chuẩn hoá về percentile trước khi gán trọng số — CCU đơn vị triệu, bài Reddit
đơn vị trăm, cộng thẳng là vô nghĩa. So sánh momentum với **cùng kỳ tuần
trước**, không phải hôm qua (gacha có chu kỳ banner, MMO reset tuần, mọi game
đều tăng cuối tuần).

## 4. `articles`

```jsonc
{
  "source_id": "ObjectId",
  "url": "...",
  "url_canonical": "...",
  "title_original": "...",
  "lang_original": "en",

  // Tự viết, KHÔNG phải trích nguyên văn
  "summary": { "vi": "...", "en": "..." },
  "title_translated": { "vi": "..." },

  "simhash": "...",             // khử trùng lặp: một tin lớn về từ 20 nguồn
  "duplicate_of": null,

  "game_ids": ["ObjectId"],
  "entity_match": {
    "method": "exact",          // exact | fuzzy | embedding | manual
    "confidence": 0.98
  },

  "category": "news",           // news | review | preview | guide | deal
  "published_at": "ISODate"
}
```

### `entity_review_queue`

Bài dưới ngưỡng tin cậy vào đây. **Mỗi lần duyệt tay phải tự động sinh alias
mới** cho `games.aliases` — không có vòng phản hồi này thì sẽ duyệt tay mãi mãi.

## 5. Người dùng

```jsonc
// users
{
  "_id": "ObjectId",
  "steam_id64": "7656...",
  "locale": "vi",
  "notification_settings": {
    "quiet_hours": { "from": "22:00", "to": "07:00" },
    "channels": { "price_alert": true, "streamer_live": true, "news_digest": "daily" }
  }
}

// user_library — chỉ lưu mức tối thiểu, có nút xoá
{
  "user_id": "ObjectId",
  "store": "steam",             // steam | epic (epic = tự khai báo)
  "game_id": "ObjectId",
  "playtime_minutes": 0,
  "synced_at": "ISODate"
}

// user_follows — game | series | developer | streamer
{ "user_id": "ObjectId", "target_type": "game", "target_id": "ObjectId" }

// price_alerts
{
  "user_id": "ObjectId",
  "game_id": "ObjectId",
  "condition": "below_price",   // below_price | discount_pct | historical_low
  "value": 200000,
  "currency": "VND",
  "triggered_at": null
}
```

**Quy tắc:** không bao giờ gửi cảnh báo giảm giá cho game đã có trong
`user_library`. Đây là lý do chính đáng để người dùng chịu mở public profile.

## 6. `streamers`

```jsonc
{
  "platform": "youtube",        // twitch | youtube | tiktok
  "channel_id": "...",
  "display_name": "...",
  "language": "vi",
  "is_live": false,
  "current_game_id": null,
  "viewers": 0,
  "websub_expires_at": "ISODate"  // YouTube WebSub phải gia hạn định kỳ
}
```

Không có nguồn tự động cho danh sách streamer Việt — curate tay ban đầu rồi mở
cho cộng đồng đề xuất. Chính danh sách này là tài sản khó sao chép nhất.
