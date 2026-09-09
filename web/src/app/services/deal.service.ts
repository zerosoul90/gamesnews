import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';

import { environment } from '../../environments/environment';

/** Thông tin game gắn kèm mỗi dòng giá. `null` nghĩa là giá trỏ tới một game
 *  không còn trong catalog — hiếm, nhưng phải phân biệt được với "chưa có ảnh". */
export interface GameDetails {
  title: string | null;
  slug: string | null;
  cover_image_url: string | null;
}

export interface Deal {
  game_id: string;
  store: string;
  price_final: number;
  price_initial: number;
  discount_percent: number;
  is_historical_low: boolean;
  is_worth_buying?: boolean;
  game_details?: GameDetails | null;
}

export interface DealResponse {
  deals: Deal[];
}

@Injectable({
  providedIn: 'root',
})
export class DealService {
  private readonly apiUrl = `${environment.apiUrl}/deals`;

  constructor(private http: HttpClient) {}

  getDeals(limit = 20, filterBy?: string): Observable<DealResponse> {
    // HttpParams thay vì nối chuỗi: giá trị lọc được mã hoá đúng, và tham số
    // rỗng bị bỏ hẳn thay vì gửi `filter_by=` — mà API khai kiểu chặt nên
    // chuỗi rỗng sẽ bị trả 422.
    let params = new HttpParams().set('limit', limit);
    if (filterBy) {
      params = params.set('filter_by', filterBy);
    }
    return this.http.get<DealResponse>(this.apiUrl, { params });
  }
}
