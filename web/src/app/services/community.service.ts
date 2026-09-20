import { Inject, Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { API_BASE_URL } from '../api-base-url';


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

/** Đúng những gì `GET /community/users/{id}/badges` trả về, không hơn.
 *
 * Endpoint trả thẳng document Mongo qua `jsonify_docs`, nên khoá là `_id` —
 * `jsonify` không đổi tên khoá — và ngoài ba trường dưới đây thì không còn gì.
 * Nguồn: `app/models/community.py::UserBadge`.
 *
 * Bản đầu khai thêm `name`, `description`, `icon_url`. Không trường nào tồn
 * tại, nên trang cá nhân in ra một lưới ô rỗng: không ảnh, tiêu đề trống, mô
 * tả trống. Không gì bắt được vì `Badge[]` chỉ là kiểu lúc biên dịch — JSON
 * thật không bị đối chiếu với nó bao giờ.
 */
export interface Badge {
  _id: string;
  user_id: string;
  badge_type: string;
  earned_at: string;
}

/** Nhãn hiển thị của một `badge_type`. */
export interface NhanHuyHieu {
  ten: string;
  moTa: string;
}

/** Chỉ `reviewer` được trao thật — `award_badge(db, user_id, "reviewer")` ở
 *  `app/api/community.py`, sau bài đánh giá đầu tiên. `first_blood` và
 *  `wiki_editor` mới chỉ là ví dụ trong chú thích của model, chưa có chỗ nào
 *  gọi, nên đừng đặt tên sẵn cho chúng: viết mô tả cho một huy hiệu không ai
 *  nhận được là tự bịa ra luật trao thưởng. */
const NHAN_THEO_LOAI: Record<string, NhanHuyHieu> = {
  reviewer: {
    ten: 'Người đánh giá',
    moTa: 'Đã viết bài đánh giá game đầu tiên.',
  },
};

/** Loại chưa có nhãn thì hiện chính `badge_type`.
 *
 * Mã thô trông kém, nhưng nó trung thực và chỉ thẳng ra loại nào còn thiếu
 * nhãn. Trả chuỗi rỗng thì ô huy hiệu lại trống y như lỗi vừa sửa.
 */
export function nhanHuyHieu(badgeType: string): NhanHuyHieu {
  return NHAN_THEO_LOAI[badgeType] ?? { ten: badgeType, moTa: '' };
}

@Injectable({
  providedIn: 'root'
})
export class CommunityService {
  private readonly apiUrl: string;
  /** `/community` trần. Hai endpoint không nằm dưới `/games` cần tới nó, và
   *  cắt chuỗi ngược từ `apiUrl` bằng `replace('/games', '')` thì hỏng ngay
   *  khi `API_BASE_URL` có sẵn đoạn `/games` ở đâu đó — `replace` thay lần
   *  khớp đầu tiên, không phải lần cuối. */
  private readonly goc: string;

  constructor(
    private http: HttpClient,
    @Inject(API_BASE_URL) apiBaseUrl: string,
  ) {
    this.goc = `${apiBaseUrl}/community`;
    this.apiUrl = `${this.goc}/games`;
  }


  getReviews(gameId: string, limit = 20, offset = 0): Observable<ReviewsResponse> {
    const params = new HttpParams().set('limit', limit).set('offset', offset);
    return this.http.get<ReviewsResponse>(`${this.apiUrl}/${gameId}/reviews`, { params });
  }

  postReview(gameId: string, score: number, comment: string | null): Observable<void> {
    // Không gửi `user_id`: chủ sở hữu lấy từ JWT, `ReviewRequest` không có
    // trường đó. `score` phải là số nguyên 1–10, khớp `Field(ge=1, le=10)`.
    return this.http.post<void>(`${this.goc}/reviews`, {
      game_id: gameId,
      score: score,
      comment: comment
    });
  }

  getBadges(userId: string): Observable<Badge[]> {
    return this.http.get<Badge[]>(`${this.goc}/users/${userId}/badges`);
  }
}
