import { Inject, Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { map } from 'rxjs/operators';
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
  /** Số game theo từng giá trị lọc, tính trên TOÀN BỘ tập khớp chứ không
   *  riêng trang này: `{ genres: { indie: 28093, ... }, platforms: {...} }`. */
  facets: Record<string, Record<string, number>>;
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

  search(query: string, page = 1, limit = 20, platform?: string, genre?: string, year?: number): Observable<SearchResponse> {
    let params = new HttpParams()
      .set('q', query)
      .set('page', page)
      // Backend nhận `per_page`. Bản trước gửi `limit`, bị lờ đi hoàn toàn, và
      // chạy đúng chỉ vì mặc định phía server cũng là 20.
      .set('per_page', limit);
    
    if (platform) {
      params = params.set('platform', platform);
    }
    if (genre) {
      params = params.set('genre', genre);
    }
    if (year) {
      params = params.set('year', year);
    }

    return this.http.get<SearchResponse>(this.apiUrl, { params });
  }

  /** Số game của từng thể loại trên cả catalog.
   *
   *  Không có endpoint riêng vì không cần: `/search` với `q` rỗng, không lọc,
   *  trả `facetDistribution` của Meilisearch trên toàn index. `per_page=1` vì
   *  chỉ cần facet — backend không cho 0. */
  genreCounts(): Observable<Record<string, number>> {
    const params = new HttpParams().set('q', '').set('per_page', 1);
    return this.http
      .get<SearchResponse>(this.apiUrl, { params })
      .pipe(map(res => res.facets?.['genres'] ?? {}));
  }
}
