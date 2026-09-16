import { Inject, Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';

import { API_BASE_URL } from '../api-base-url';

/** Nguồn của bài. `null` khi nguồn đã bị xoá khỏi bảng `sources` — hiếm, nhưng
 *  phải phân biệt được với "chưa biết tên nguồn". */
export interface ArticleSource {
  name: string | null;
  language: string | null;
}

/** Game mà bài nói tới. Chỉ khoảng 1/7 số bài gắn được game, nên `null` là ca
 *  THƯỜNG GẶP chứ không phải ngoại lệ — đừng render mặc định một khung ảnh vỡ. */
export interface ArticleGame {
  title: string | null;
  slug: string | null;
  cover_image_url: string | null;
}

export interface Article {
  id: string;
  /** Tiêu đề tiếng Việt nếu có, nếu không thì bản gốc. API đã tự chọn. */
  title: string | null;
  /** Tóm tắt TỰ VIẾT. API không bao giờ trả nguyên văn bài gốc — xem
   *  `app/services/news_feed.py`. */
  summary: string | null;
  /** Link ra nguồn gốc: muốn đọc đủ thì bấm sang trang của họ. */
  url: string | null;
  published_at: string | null;
  source: ArticleSource | null;
  game: ArticleGame | null;
}

export interface NewsResponse {
  articles: Article[];
  total: number;
  limit: number;
  offset: number;
}

@Injectable({
  providedIn: 'root',
})
export class NewsService {
  private readonly apiUrl: string;

  constructor(
    private http: HttpClient,
    @Inject(API_BASE_URL) apiBaseUrl: string,
  ) {
    this.apiUrl = `${apiBaseUrl}/news`;
  }

  getNews(limit = 20, offset = 0, gameId?: string): Observable<NewsResponse> {
    let params = new HttpParams().set('limit', limit).set('offset', offset);
    if (gameId) {
      params = params.set('game_id', gameId);
    }
    return this.http.get<NewsResponse>(this.apiUrl, { params });
  }
}
