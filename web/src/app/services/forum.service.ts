import { Inject, Injectable } from '@angular/core';
import { HttpClient, HttpErrorResponse, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';

import { API_BASE_URL } from '../api-base-url';

/*
 * Kiểu dữ liệu chép từ model Pydantic ở `app/api/forum.py` — nguồn sự thật là
 * `response_model` của từng endpoint, không phải ý tưởng về một diễn đàn nên
 * có gì. Không có `avatar`, không có `steam_id64`: API cố ý không trả chúng.
 */

export interface TacGia {
  id: string;
  /** `null` = user chưa đặt biệt danh hoặc đã bị xoá. */
  nickname: string | null;
}

export interface GameRef {
  id: string;
  slug: string | null;
  title: string | null;
}

export interface ChuDeTomTat {
  id: string;
  title: string;
  category: string | null;
  game: GameRef | null;
  author: TacGia;
  reply_count: number;
  locked: boolean;
  created_at: string;
  last_post_at: string;
}

export interface ChuDeChiTiet extends ChuDeTomTat {
  body: string;
  edited_at: string | null;
}

export interface TrichDan {
  id: string;
  /** Cả hai `null` = bài được trích đã bị ẩn hoặc xoá. */
  author: TacGia | null;
  body: string | null;
}

export interface BaiTraLoi {
  id: string;
  author: TacGia;
  body: string;
  quote: TrichDan | null;
  created_at: string;
  edited_at: string | null;
}

export interface ChuyenMuc {
  slug: string;
  name: string;
  description: string;
  thread_count: number;
}

export interface DanhSachChuDe {
  items: ChuDeTomTat[];
  total: number;
  page: number;
  per_page: number;
}

export interface TrangChuDe {
  thread: ChuDeChiTiet;
  posts: BaiTraLoi[];
  total_posts: number;
  page: number;
  per_page: number;
}

export interface TrangThaiDang {
  nickname: string | null;
  can_post: boolean;
  /** Lý do chưa đăng được, viết sẵn bằng tiếng Việt ở backend. */
  reason: string | null;
}

/** Nơi một chủ đề mới thuộc về — đúng một trong hai, backend trả 422 nếu không. */
export type NoiDang = { category: string } | { game_id: string };

/**
 * Câu báo lỗi đọc được từ một lỗi HTTP của diễn đàn.
 *
 * `ForumError` ở backend trả `{detail: "chuỗi tiếng Việt"}` — hiện thẳng được.
 * Lỗi validate của Pydantic thì `detail` là MẢNG object; in thẳng ra là
 * "[object Object]", nên lấy `msg` của mục đầu và bỏ tiền tố "Value error, ".
 */
export function cauBaoLoi(err: unknown, macDinh = 'Có lỗi xảy ra, thử lại sau.'): string {
  if (!(err instanceof HttpErrorResponse)) {
    return macDinh;
  }
  const detail = err.error?.detail;
  if (typeof detail === 'string') {
    return detail;
  }
  if (Array.isArray(detail) && typeof detail[0]?.msg === 'string') {
    return detail[0].msg.replace(/^Value error, /, '');
  }
  if (err.status === 401) {
    return 'Phiên đăng nhập đã hết hạn — đăng nhập lại.';
  }
  return macDinh;
}

@Injectable({ providedIn: 'root' })
export class ForumService {
  private readonly goc: string;

  constructor(
    private http: HttpClient,
    @Inject(API_BASE_URL) apiBaseUrl: string,
  ) {
    this.goc = `${apiBaseUrl}/api/v1/forum`;
  }

  chuyenMuc(): Observable<ChuyenMuc[]> {
    return this.http.get<ChuyenMuc[]>(`${this.goc}/categories`);
  }

  danhSach(noi: NoiDang, page = 1): Observable<DanhSachChuDe> {
    let params = new HttpParams().set('page', page);
    params = 'category' in noi ? params.set('category', noi.category) : params.set('game_id', noi.game_id);
    return this.http.get<DanhSachChuDe>(`${this.goc}/threads`, { params });
  }

  chuDe(id: string, page = 1): Observable<TrangChuDe> {
    const params = new HttpParams().set('page', page);
    return this.http.get<TrangChuDe>(`${this.goc}/threads/${id}`, { params });
  }

  trangThai(): Observable<TrangThaiDang> {
    return this.http.get<TrangThaiDang>(`${this.goc}/me`);
  }

  datBietDanh(nickname: string): Observable<TrangThaiDang> {
    return this.http.put<TrangThaiDang>(`${this.goc}/me/nickname`, { nickname });
  }

  taoChuDe(noi: NoiDang, title: string, body: string): Observable<{ id: string }> {
    return this.http.post<{ id: string }>(`${this.goc}/threads`, { ...noi, title, body });
  }

  traLoi(threadId: string, body: string, quotePostId: string | null): Observable<{ id: string }> {
    return this.http.post<{ id: string }>(`${this.goc}/threads/${threadId}/posts`, {
      body,
      quote_post_id: quotePostId,
    });
  }

  baoCao(targetType: 'thread' | 'post', targetId: string, reason: string): Observable<{ hidden: boolean }> {
    return this.http.post<{ hidden: boolean }>(`${this.goc}/reports`, {
      target_type: targetType,
      target_id: targetId,
      reason,
    });
  }

  xoaChuDe(id: string): Observable<void> {
    return this.http.delete<void>(`${this.goc}/threads/${id}`);
  }

  xoaTraLoi(id: string): Observable<void> {
    return this.http.delete<void>(`${this.goc}/posts/${id}`);
  }
}
