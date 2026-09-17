import { Inject, Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { API_BASE_URL } from '../api-base-url';

export interface SearchHit {
  id: string;
  slug: string;
  titles: { primary: string; vi: string | null; ja: string | null };
  platforms: string[];
  genres: string[];
  type: string;
  release_year: number | null;
  cover: string | null;
}

export interface SearchResponse {
  query: string;
  total: number;
  page: number;
  per_page: number;
  hits: SearchHit[];
}

@Injectable({
  providedIn: 'root'
})
export class SearchService {
  private readonly apiUrl: string;

  constructor(
    private http: HttpClient,
    @Inject(API_BASE_URL) apiBaseUrl: string,
  ) {
    this.apiUrl = `${apiBaseUrl}/search`;
  }

  search(query: string, page = 1, limit = 20): Observable<SearchResponse> {
    const params = new HttpParams()
      .set('q', query)
      .set('page', page)
      .set('limit', limit);
    return this.http.get<SearchResponse>(this.apiUrl, { params });
  }
}
