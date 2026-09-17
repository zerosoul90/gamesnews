import { Inject, Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { API_BASE_URL } from '../api-base-url';
import { User } from './auth.service';
import { Article } from './news.service';

export interface FollowsResponse {
  articles: Article[];
}

export interface WrappedData {
  year: number;
  total_games_played: number;
  total_hours: number;
  top_genre: string;
  top_game: string;
}

@Injectable({
  providedIn: 'root'
})
export class UserService {
  private readonly apiUrl: string;

  constructor(
    private http: HttpClient,
    @Inject(API_BASE_URL) apiBaseUrl: string,
  ) {
    this.apiUrl = `${apiBaseUrl}/me`;
  }

  getProfile(): Observable<User> {
    return this.http.get<User>(this.apiUrl);
  }

  getFollowsFeed(): Observable<FollowsResponse> {
    return this.http.get<FollowsResponse>(`${this.apiUrl}/follows`);
  }

  getWrapped(year: number): Observable<WrappedData> {
    return this.http.get<WrappedData>(`${this.apiUrl}/wrapped?year=${year}`);
  }
}
