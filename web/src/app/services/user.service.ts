import { Inject, Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

import { API_BASE_URL } from '../api-base-url';

/** Thẻ game rút gọn mà backend gắn kèm. Nguồn: `app/services/game_cards.py`. */
export interface GameCard {
  title: string | null;
  slug: string | null;
  cover_image_url: string | null;
}

/**
 * Một mục đang theo dõi.
 *
 * `target` là `null` với mục không phải game (series, studio, streamer) — đó
 * là trạng thái bình thường, không phải lỗi tải. Giao diện phải hiển thị được
 * bằng `target_id` trần.
 */
export interface Follow {
  id: string;
  target_type: string;
  target_id: string;
  target: GameCard | null;
}

export interface FollowsResponse {
  follows: Follow[];
  total: number;
}

export interface LibraryItem {
  game_id: string;
  store: string;
  playtime_minutes: number;
  synced_at: string;
  game: GameCard | null;
}

export interface LibraryResponse {
  items: LibraryItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface SyncResponse {
  synced: number;
  skipped: number;
}

export interface WrappedTopGame {
  game_id: string;
  title: string;
  playtime_minutes: number;
}

/**
 * Tổng kết năm. Khai đúng theo `app/services/wrapped.py`.
 *
 * Bản trước khai `total_hours`, `top_genre`, `top_game` — không trường nào
 * trong ba cái đó được backend trả về, nên giao diện chỉ hiện ô trống.
 */
export interface WrappedData {
  year: number;
  total_games_played: number;
  total_playtime_minutes: number;
  top_games: WrappedTopGame[];
  message: string;
}

@Injectable({
  providedIn: 'root',
})
export class UserService {
  private readonly apiUrl: string;

  constructor(
    private http: HttpClient,
    @Inject(API_BASE_URL) apiBaseUrl: string,
  ) {
    // `/api/v1/user`, không phải `/me`. Nhóm endpoint cá nhân hoá nằm dưới
    // tiền tố này (xem `app/api/user.py`); `/me/...` trả 404.
    this.apiUrl = `${apiBaseUrl}/api/v1/user`;
  }

  getFollows(): Observable<FollowsResponse> {
    return this.http.get<FollowsResponse>(`${this.apiUrl}/follows`);
  }

  /** Bỏ theo dõi theo `_id` của chính mục đó, không phải theo `target_id`. */
  unfollow(followId: string): Observable<{ status: string }> {
    return this.http.delete<{ status: string }>(`${this.apiUrl}/follows/${followId}`);
  }

  /** Năm nằm trong **đường dẫn**, không phải query string. */
  getWrapped(year: number): Observable<WrappedData> {
    return this.http.get<WrappedData>(`${this.apiUrl}/me/wrapped/${year}`);
  }

  follow(targetType: 'game' | 'series' | 'developer' | 'streamer', targetId: string): Observable<{ status: string, followed: boolean }> {
    return this.http.post<{ status: string, followed: boolean }>(`${this.apiUrl}/follows`, {
      target_type: targetType,
      target_id: targetId
    });
  }

  getLibrary(limit: number = 50, offset: number = 0): Observable<LibraryResponse> {
    return this.http.get<LibraryResponse>(`${this.apiUrl}/library`, {
      params: { limit: limit.toString(), offset: offset.toString() }
    });
  }

  syncLibrary(): Observable<SyncResponse> {
    return this.http.post<SyncResponse>(`${this.apiUrl}/library/sync`, {});
  }

  deleteLibrary(): Observable<{ deleted_count: number }> {
    return this.http.delete<{ deleted_count: number }>(`${this.apiUrl}/library`);
  }
}
