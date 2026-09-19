import { Component, Inject, OnInit, PLATFORM_ID } from '@angular/core';
import { CommonModule, isPlatformBrowser } from '@angular/common';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';

import { AuthService } from '../../services/auth.service';

/**
 * Nơi Steam trả người dùng về sau khi đăng nhập.
 *
 * Steam chuyển hướng trình duyệt tới `{FRONTEND_URL}/auth/steam/callback` kèm
 * một chùm tham số `openid.*`. Trang này chuyển tiếp nguyên văn chùm ấy sang
 * backend để đổi lấy JWT, rồi đưa người dùng về trang chủ.
 *
 * **Vì sao không để Steam trỏ thẳng vào endpoint của backend.** Endpoint ấy
 * trả JSON. Người dùng sẽ kết thúc hành trình đăng nhập bằng cách nhìn một cục
 * `{"access_token": ...}` trên màn hình trắng, và token không bao giờ tới được
 * `localStorage` của ứng dụng. Phải có một trang của chính SPA đứng ra nhận.
 */
@Component({
  selector: 'app-steam-callback',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './steam-callback.component.html',
})
export class SteamCallbackComponent implements OnInit {
  loi: string | null = null;

  private readonly laTrinhDuyet: boolean;

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private authService: AuthService,
    @Inject(PLATFORM_ID) platformId: object,
  ) {
    this.laTrinhDuyet = isPlatformBrowser(platformId);
  }

  ngOnInit(): void {
    // Chỉ đổi token ở trình duyệt. Phản hồi OpenID của Steam dùng **một lần**:
    // nếu SSR cũng gọi `check_authentication` thì lượt của server tiêu mất chữ
    // ký, và lượt của trình duyệt ngay sau đó nhận 401. Lỗi này chỉ xuất hiện
    // khi chạy có SSR, tức đúng cấu hình production.
    if (!this.laTrinhDuyet) {
      return;
    }

    const params = this.route.snapshot.queryParams as Record<string, string>;
    if (!params['openid.claimed_id']) {
      this.loi = 'Thiếu tham số từ Steam. Hãy bắt đầu lại từ trang đăng nhập.';
      return;
    }

    this.authService.completeSteamLogin(params).subscribe({
      next: () => this.router.navigate(['/'], { replaceUrl: true }),
      error: () => {
        this.loi = 'Steam không xác thực được phiên này. Hãy thử đăng nhập lại.';
      },
    });
  }
}
