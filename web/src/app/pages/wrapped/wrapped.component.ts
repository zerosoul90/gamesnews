import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';

import { UserService, WrappedData } from '../../services/user.service';
import { AuthService } from '../../services/auth.service';

/**
 * Tổng kết năm.
 *
 * Ba trong năm trường bản trước đọc (`total_hours`, `top_genre`, `top_game`)
 * không có trong phản hồi của backend, nên kể cả khi gọi đúng đường dẫn thì ba
 * ô to nhất trang vẫn trống. Backend trả `total_playtime_minutes` và mảng
 * `top_games`; giờ chơi quy đổi ở đây chứ không đòi backend đổi hợp đồng.
 */
@Component({
  selector: 'app-wrapped',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './wrapped.component.html',
})
export class WrappedComponent implements OnInit {
  wrappedData: WrappedData | null = null;
  dangTai = true;
  canDangNhap = false;
  /** Đã đăng nhập nhưng chưa đồng bộ thư viện — backend trả 404 kèm "chưa đủ
   *  dữ liệu". Đây không phải lỗi, và lời mời đúng là đi đồng bộ, không phải
   *  "thử lại sau". */
  chuaDuDuLieu = false;
  loi: string | null = null;
  currentYear = new Date().getFullYear();

  constructor(
    private userService: UserService,
    private authService: AuthService,
  ) {}

  ngOnInit(): void {
    this.tai(this.currentYear);
  }

  tai(year: number): void {
    if (!this.authService.isLoggedIn()) {
      this.canDangNhap = true;
      this.dangTai = false;
      return;
    }

    this.dangTai = true;
    this.loi = null;
    this.chuaDuDuLieu = false;
    this.userService.getWrapped(year).subscribe({
      next: (data) => {
        this.wrappedData = data;
        this.dangTai = false;
      },
      error: (err) => {
        this.dangTai = false;
        if (err.status === 401) {
          this.canDangNhap = true;
        } else if (err.status === 404) {
          this.chuaDuDuLieu = true;
        } else {
          this.loi = 'Không tải được tổng kết năm. Thử lại sau ít phút.';
        }
      },
    });
  }

  /** Giờ chơi, làm tròn xuống. Backend chỉ trả phút. */
  get tongGio(): number {
    return Math.floor((this.wrappedData?.total_playtime_minutes ?? 0) / 60);
  }

  get gameDauBang(): string | null {
    return this.wrappedData?.top_games?.[0]?.title ?? null;
  }
}
