import { Inject, Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { API_BASE_URL } from '../api-base-url';
import { GameDetails } from './deal.service';

export interface WatchlistItem {
  id: string;
  user_id: string;
  game_id: string;
  added_at: string;
  target_price: number | null;
  game?: GameDetails;
}

export interface WatchlistResponse {
  items: WatchlistItem[];
  total: number;
}

@Injectable({
  providedIn: 'root'
})
export class WatchlistService {
  private readonly apiUrl: string;

  constructor(
    private http: HttpClient,
    @Inject(API_BASE_URL) apiBaseUrl: string,
  ) {
    this.apiUrl = `${apiBaseUrl}/me/watchlist`;
  }

  getWatchlist(): Observable<WatchlistResponse> {
    return this.http.get<WatchlistResponse>(this.apiUrl);
  }

  addToWatchlist(gameId: string, targetPrice?: number): Observable<WatchlistItem> {
    const payload: any = { game_id: gameId };
    if (targetPrice !== undefined) {
      payload.target_price = targetPrice;
    }
    return this.http.post<WatchlistItem>(this.apiUrl, payload);
  }

  removeFromWatchlist(gameId: string): Observable<void> {
    return this.http.delete<void>(`${this.apiUrl}/${gameId}`);
  }
}
