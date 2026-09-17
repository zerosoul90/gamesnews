import { Inject, Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { API_BASE_URL } from '../api-base-url';

export interface CommunityScore {
  is_hidden: boolean;
  average_score: number | null;
  review_count: number;
}

export interface Review {
  id: string;
  user_id: string;
  score: number;
  comment: string;
  created_at: string;
}

export interface ReviewsResponse {
  reviews: Review[];
  total: number;
  limit: number;
  offset: number;
}

@Injectable({
  providedIn: 'root'
})
export class CommunityService {
  private readonly apiUrl: string;

  constructor(
    private http: HttpClient,
    @Inject(API_BASE_URL) apiBaseUrl: string,
  ) {
    this.apiUrl = `${apiBaseUrl}/community/games`;
  }

  getScore(gameId: string): Observable<CommunityScore> {
    return this.http.get<CommunityScore>(`${this.apiUrl}/${gameId}/reviews/score`);
  }

  getReviews(gameId: string, limit = 20, offset = 0): Observable<ReviewsResponse> {
    const params = new HttpParams().set('limit', limit).set('offset', offset);
    return this.http.get<ReviewsResponse>(`${this.apiUrl}/${gameId}/reviews`, { params });
  }
}
