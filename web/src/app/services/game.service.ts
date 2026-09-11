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
