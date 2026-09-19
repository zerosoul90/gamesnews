import { Inject, Injectable, PLATFORM_ID } from '@angular/core';
import { isPlatformBrowser } from '@angular/common';
import { HttpClient, HttpParams } from '@angular/common/http';
import { BehaviorSubject, Observable, tap } from 'rxjs';

import { API_BASE_URL } from '../api-base-url';

/**
 * Phiên đăng nhập. Hệ thống này **chỉ có định danh Steam** — không email,
 * không mật khẩu, không tên hiển thị.
 *
 * Bản trước khai thêm `email`, `username`, `avatar_url` và gọi `/auth/login`,
 * `/auth/register`. Không endpoint nào trong hai cái đó tồn tại (404), và ba
 * trường kia không nằm trong bất kỳ phản hồi nào của backend. Giao diện dựng
 * trên chúng chỉ có thể hiển thị `undefined`.
 *
 * Nguồn sự thật là `app/api/auth.py`: `/api/v1/auth/steam/callback` trả đúng
 * bốn trường dưới đây.
 */
export interface SteamSession {
  user_id: string;
  steam_id64: string;
}

/** Phản hồi thật của `GET /api/v1/auth/steam/callback`. */
export interface SteamCallbackResponse {
  access_token: string;
  token_type: string;
  steam_id64: string;
  user_id: string;
}

const KHOA_TOKEN = 'token';
const KHOA_PHIEN = 'steam_session';

@Injectable({
  providedIn: 'root',
})
export class AuthService {
  private readonly apiUrl: string;
  private readonly laTrinhDuyet: boolean;
  private phienHienTai = new BehaviorSubject<SteamSession | null>(null);

  /** Phiên đang đăng nhập, `null` khi chưa. Nav và trang cá nhân đều nghe ở đây. */
  readonly currentUser$ = this.phienHienTai.asObservable();

  constructor(
    private http: HttpClient,
    @Inject(API_BASE_URL) private apiBaseUrl: string,
    @Inject(PLATFORM_ID) platformId: object,
  ) {
    this.apiUrl = `${apiBaseUrl}/api/v1/auth`;
    // `isPlatformBrowser` chứ không phải `typeof localStorage !== 'undefined'`:
    // Node 22+ có localStorage thật sau một cờ chạy, nên phép thử kia sẽ âm
    // thầm đọc/ghi một kho lưu trữ *của server* dùng chung cho mọi người dùng.
    this.laTrinhDuyet = isPlatformBrowser(platformId);
    this.napPhienTuKho();
  }

  get currentUserValue(): SteamSession | null {
    return this.phienHienTai.value;
  }

  isLoggedIn(): boolean {
    return this.currentUserValue !== null;
  }

  getToken(): string | null {
    return this.laTrinhDuyet ? localStorage.getItem(KHOA_TOKEN) : null;
  }

  /**
   * URL để đẩy trình duyệt sang Steam.
   *
   * Phải là điều hướng cả trang (`location.href`), không phải `HttpClient`:
   * backend trả 302 sang `steamcommunity.com` và người dùng cần *nhìn thấy*
   * trang đăng nhập của Steam để nhập mật khẩu. Gọi bằng XHR thì trình duyệt
   * tự đi theo redirect trong nền rồi nhận về HTML của Steam — không ai đăng
   * nhập được.
   */
  steamLoginUrl(): string {
    return `${this.apiUrl}/steam/login`;
  }

  /**
   * Đổi tham số OpenID mà Steam trả về lấy JWT.
   *
   * Truyền lại **nguyên văn** mọi tham số: chữ ký của Steam ký trên đúng tập
   * tham số ấy, nên bỏ hay sửa một cái là hỏng xác thực. Backend chỉ chuyển
   * tiếp chúng sang `check_authentication`.
   */
  completeSteamLogin(queryParams: Record<string, string>): Observable<SteamCallbackResponse> {
    let params = new HttpParams();
    for (const [khoa, giaTri] of Object.entries(queryParams)) {
      params = params.set(khoa, giaTri);
    }
    return this.http
      .get<SteamCallbackResponse>(`${this.apiUrl}/steam/callback`, { params })
      .pipe(tap((res) => this.luuPhien(res)));
  }

  logout(): void {
    if (this.laTrinhDuyet) {
      localStorage.removeItem(KHOA_TOKEN);
      localStorage.removeItem(KHOA_PHIEN);
    }
    this.phienHienTai.next(null);
  }

  private luuPhien(res: SteamCallbackResponse): void {
    const phien: SteamSession = { user_id: res.user_id, steam_id64: res.steam_id64 };
    if (this.laTrinhDuyet) {
      localStorage.setItem(KHOA_TOKEN, res.access_token);
      localStorage.setItem(KHOA_PHIEN, JSON.stringify(phien));
    }
    this.phienHienTai.next(phien);
  }

  private napPhienTuKho(): void {
    if (!this.laTrinhDuyet) {
      return;
    }
    // Không có token thì phiên lưu lại cũng vô nghĩa: mọi lời gọi có xác thực
    // sẽ 401, mà nav lại hiện như đang đăng nhập. Dọn luôn cho hai thứ khớp nhau.
    const token = localStorage.getItem(KHOA_TOKEN);
    const thoPhien = localStorage.getItem(KHOA_PHIEN);
    if (!token || !thoPhien) {
      return;
    }
    try {
      this.phienHienTai.next(JSON.parse(thoPhien) as SteamSession);
    } catch {
      localStorage.removeItem(KHOA_PHIEN);
    }
  }
}
