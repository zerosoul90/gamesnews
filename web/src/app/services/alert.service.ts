import { Inject, Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

import { API_BASE_URL } from '../api-base-url';
import { GameCard } from './user.service';

/**
 * Một cảnh báo giá.
 *
 * Thay cho `WatchlistService` cũ, vốn gọi `/me/watchlist` — một endpoint không
 * tồn tại, cho một khái niệm backend cũng không có. Thứ gần nhất và có thật là
 * cảnh báo giá: người dùng chọn game + mức giá muốn được báo.
 */
export interface PriceAlert {
  id: string;
  game_id: string;
  condition: string;
  value: number | null;
  currency: string;
  triggered_at: string | null;
  /**
   * Game này đã nằm trong thư viện của người dùng.
   *
   * Cảnh báo ấy sẽ **không bao giờ được gửi** — `services/notification.py`
   * chặn, và chặn kiểu fail-closed. Backend vẫn trả về kèm cờ thay vì giấu đi,
   * nên giao diện có trách nhiệm làm mờ và nói rõ lý do; im lặng bỏ qua cờ này
   * thì người dùng ngồi đợi một thông báo không bao giờ tới.
   */
  owned: boolean;
  game: GameCard | null;
}

export interface AlertsResponse {
  alerts: PriceAlert[];
  total: number;
}

@Injectable({
  providedIn: 'root',
})
export class AlertService {
  private readonly apiUrl: string;

  constructor(
    private http: HttpClient,
    @Inject(API_BASE_URL) apiBaseUrl: string,
  ) {
    this.apiUrl = `${apiBaseUrl}/api/v1/user/alerts`;
  }

  getAlerts(): Observable<AlertsResponse> {
    return this.http.get<AlertsResponse>(this.apiUrl);
  }

  /**
   * Đặt một cảnh báo.
   *
   * `historical_low` là điều kiện duy nhất không cần `value`, nên nó là thứ
   * bấm-một-nút dùng được từ trang game. Hai điều kiện kia (`below_price`,
   * `discount_pct`) cần người dùng nhập một con số — chưa có giao diện cho
   * chúng, và đoán hộ một ngưỡng thì cảnh báo sẽ nổ sai lúc.
   */
  themCanhBao(
    gameId: string,
    condition: 'below_price' | 'discount_pct' | 'historical_low' = 'historical_low',
    value: number | null = null,
  ): Observable<{ status: string }> {
    return this.http.post<{ status: string }>(this.apiUrl, {
      game_id: gameId,
      condition,
      value,
    });
  }

  /** Xoá theo `_id` của cảnh báo. Backend kẹp thêm `user_id` nên không xoá
   *  được cảnh báo của người khác dù có đoán trúng id. */
  deleteAlert(alertId: string): Observable<{ status: string }> {
    return this.http.delete<{ status: string }>(`${this.apiUrl}/${alertId}`);
  }
}
