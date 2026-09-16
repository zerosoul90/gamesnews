import { Inject, Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';

import { API_BASE_URL } from '../api-base-url';

/** Thông tin game gắn kèm mỗi dòng giá. `null` nghĩa là giá trỏ tới một game
 *  không còn trong catalog — hiếm, nhưng phải phân biệt được với "chưa có ảnh". */
export interface GameDetails {
  title: string | null;
  slug: string | null;
  cover_image_url: string | null;
}

export interface Deal {
  game_id: string;
  store: string;
  price_final: number;
  price_initial: number;
  discount_percent: number;
  is_historical_low: boolean;
  is_worth_buying?: boolean;
  game_details?: GameDetails | null;
}

export interface DealResponse {
  deals: Deal[];
}

/** Game đang được tặng. Cùng collection `price_current` với `Deal`, khác ở chỗ
 *  `is_free_promo` bật và có mốc kết thúc đợt tặng. */
export interface FreeGame {
  game_id: string;
  store: string;
  price_initial: number;
  price_final: number;
  /** Mốc hết hạn đợt tặng, ISO-8601. `null` khi store không công bố — lúc đó
   *  không được bịa ra một cái đếm ngược. */
  promo_ends_at: string | null;
  /** Link đi nhận game tại store. */
  url: string | null;
  game_details?: GameDetails | null;
}

export interface FreeGameResponse {
  free_games: FreeGame[];
}

@Injectable({
  providedIn: 'root',
})
export class DealService {
  private readonly apiUrl: string;
  private readonly baseUrl: string;

  constructor(
    private http: HttpClient,
    @Inject(API_BASE_URL) apiBaseUrl: string,
  ) {
    this.baseUrl = apiBaseUrl;
    this.apiUrl = `${apiBaseUrl}/deals`;
  }

  getDeals(limit = 20, filterBy?: string): Observable<DealResponse> {
    // HttpParams thay vì nối chuỗi: giá trị lọc được mã hoá đúng, và tham số
    // rỗng bị bỏ hẳn thay vì gửi `filter_by=` — mà API khai kiểu chặt nên
    // chuỗi rỗng sẽ bị trả 422.
    let params = new HttpParams().set('limit', limit);
    if (filterBy) {
      params = params.set('filter_by', filterBy);
    }
    return this.http.get<DealResponse>(this.apiUrl, { params });
  }

  /** Game đang được tặng miễn phí.
   *
   *  Đặt cùng service với `getDeals` vì hai endpoint đọc cùng một collection ở
   *  backend (`price_current`) và cùng một khái niệm nghiệp vụ — khuyến mãi.
   *  Tách ra thành service riêng chỉ để đổi một đoạn đường dẫn là thêm một lớp
   *  không mang thông tin nào. */
  getFreeGames(limit = 20): Observable<FreeGameResponse> {
    const params = new HttpParams().set('limit', limit);
    return this.http.get<FreeGameResponse>(`${this.baseUrl}/free-games`, { params });
  }
}
