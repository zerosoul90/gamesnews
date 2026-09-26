import { Inject, Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';

import { API_BASE_URL } from '../api-base-url';
import { GameDetails } from './deal.service';

export type HotBoard = 'popular' | 'rising';

/** Giá Steam VN của game, nếu đang theo dõi. `null` ở `HotGame.price` nghĩa là
 *  chưa có giá VN (game free-to-play, hoặc chưa tới lượt đọc giá). */
export interface HotPrice {
  price_final: number;
  discount_percent: number;
  is_historical_low: boolean;
}

export interface HotGame {
  rank: number;
  game_id: string;
  game_details: GameDetails;
  /** Người đang chơi trên Steam, lượt đo gần nhất trong 24 giờ. */
  ccu_now: number;
  score_absolute: number;
  score_momentum: number;
  price: HotPrice | null;
}

export interface HotResponse {
  board: HotBoard;
  /** Mốc tính bảng, ISO-8601. `null` khi chưa tính lần nào. */
  computed_at: string | null;
  games: HotGame[];
}

@Injectable({ providedIn: 'root' })
export class HotService {
  private readonly apiUrl: string;

  constructor(
    private http: HttpClient,
    @Inject(API_BASE_URL) apiBaseUrl: string,
  ) {
    this.apiUrl = `${apiBaseUrl}/hot`;
  }

  getHot(board: HotBoard, limit = 20): Observable<HotResponse> {
    const params = new HttpParams().set('board', board).set('limit', limit);
    return this.http.get<HotResponse>(this.apiUrl, { params });
  }
}
