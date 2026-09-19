import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';

import { AuthService } from '../../services/auth.service';

/**
 * Trang đăng nhập. Chỉ có một đường: Steam OpenID.
 *
 * Bản trước là form email + mật khẩu gọi `/auth/login` và `/auth/register` —
 * cả hai đều 404. Tài khoản email/mật khẩu cũng không nằm trong phạm vi:
 * `docs/CLAUDE.md` chặn việc lưu dữ liệu người dùng quá mức cần, mà email +
 * hash mật khẩu là đúng thứ đó.
 */
@Component({
  selector: 'app-auth',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './auth.component.html',
})
export class AuthComponent {
  constructor(private authService: AuthService) {}

  /**
   * Rời khỏi ứng dụng sang Steam.
   *
   * `window.location.href` chứ không phải `Router`: đích nằm ngoài Angular.
   */
  dangNhapSteam(): void {
    window.location.href = this.authService.steamLoginUrl();
  }
}
