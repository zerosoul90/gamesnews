import { Inject, Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';

import { API_BASE_URL } from '../api-base-url';

/** Một mốc phát hành. Là mảng theo region + platform, không phải một trường
 *  duy nhất — một game ra PC ở Nhật trước, ra console ở phương Tây sau. */
export interface ReleaseDate {
  region: string;
  date: string | null;
  platform: string | null;
}

export interface GamePrice {
  store: string;
  region: string;
  currency: string;
  price_final: number;
  price_initial: number;
  discount_percent: number;
  is_historical_low: boolean;
  /** Đợt tặng miễn phí (Epic). `promo_ends_at` là hạn chót nhận. */
  is_free_promo?: boolean;
  promo_ends_at?: string | null;
  /** URL trang sản phẩm ở store, khi nguồn có trả. */
  url?: string | null;
}

export interface PriceHistoryPoint {
  changed_at: string;
  price_final: number;
}

export interface SystemRequirements {
  minimum: Record<string, string>;
  recommended: Record<string, string>;
}

/** Dưới ngưỡng review thì `average_score` là `null`, không phải một con số bị
 *  đánh dấu — chống review bombing, xem PHASE-8.md. */
export interface CommunityScore {
  average_score: number | null;
  review_count: number;
  is_hidden: boolean;
}

/** Một ngày trong chuỗi số người chơi đồng thời, từ bảng gộp ngày của backend.
 *  `samples` là số lần đo thật trong ngày — ngày job chỉ chạy được 1 lượt không
 *  nên đọc ngang với ngày đủ 96 lượt. */
export interface PlayerCountDay {
  date: string;
  avg: number | null;
  peak: number | null;
  min: number | null;
  max: number | null;
  samples: number | null;
}

/** Điểm đánh giá từ Steam. Là một thứ KHÁC `CommunityScore`: thang khác, nhóm
 *  người khác. `positive_percent` mới là con số phân biệt được — `score` của
 *  Steam chỉ là nhóm thô 0-9, cả game 1,15 triệu review và game 84 review đều
 *  ra 8 / "Very Positive". `null` nghĩa là chưa đọc được, không phải 0 điểm. */
export interface SteamReview {
  score: number;
  score_desc: string;
  positive: number;
  negative: number;
  total: number;
  positive_percent: number;
  checked_at?: string;
}

/** Một dòng giá quốc tế. `price_cents` là **cent USD**, không phải đồng — tên
 *  field nói rõ thang đo vì `GamePrice.price_final` ở ngay cạnh là VND đơn vị
 *  lớn, và trộn hai thứ là in một con số USD kèm dấu ₫. */
export interface IntlDeal {
  store: string;
  store_id: string;
  price_cents: number;
  retail_price_cents: number | null;
  savings_percent: number;
  url: string | null;
}

/** Giá nhiều store từ CheapShark, USD. Tách hẳn khỏi `prices` (VND) và KHÔNG
 *  tham gia phép so "rẻ nhất" của bảng giá VND. `null` nghĩa là chưa đọc được. */
export interface IntlPrices {
  source?: string;
  currency: string;
  deals: IntlDeal[];
  lowest_ever_cents: number | null;
  lowest_ever_at: number | null;
  checked_at?: string;
}

export interface GameDetail {
  id: string;
  slug: string;
  title: string;
  title_primary: string;
  type: string | null;
  series: string | null;
  platforms: string[];
  genres: string[];
  developers: string[];
  publishers: string[];
  release_dates: ReleaseDate[];
  is_live_service: boolean;
  current_season: string | null;
  cover_image_url: string | null;
  screenshots: string[];
  system_requirements: SystemRequirements;
  region_locked_vn: boolean;
  steam_appid: number | null;
  region: string;
  prices: GamePrice[];
  price_history: PriceHistoryPoint[];
  community_score: CommunityScore;
  steam_review: SteamReview | null;
  intl_prices: IntlPrices | null;
  player_counts: PlayerCountDay[];
}

@Injectable({
  providedIn: 'root',
})
export class GameService {
  private readonly apiUrl: string;

  constructor(
    private http: HttpClient,
    @Inject(API_BASE_URL) apiBaseUrl: string,
  ) {
    this.apiUrl = `${apiBaseUrl}/games/by-slug`;
  }

  /** Một lần gọi cho cả trang: game + giá + lịch sử giá + điểm cộng đồng.
   *  SSR render trên server nên mỗi lần gọi là một round-trip nằm thẳng trong
   *  thời gian chờ của người dùng. */
  getBySlug(slug: string, historyDays = 30): Observable<GameDetail> {
    const params = new HttpParams().set('history_days', historyDays);
    // encodeURIComponent: slug tới từ URL, không phải từ danh sách ta kiểm soát.
    return this.http.get<GameDetail>(`${this.apiUrl}/${encodeURIComponent(slug)}`, { params });
  }
}
