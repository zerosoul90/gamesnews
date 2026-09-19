import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';

import { AlertService, PriceAlert } from '../../services/alert.service';
import { AuthService } from '../../services/auth.service';

/**
 * "Cảnh báo giá của tôi".
 *
 * Trước đây là trang `/watchlist` gọi `/me/watchlist` — 404 trên mọi lượt tải.
 * Lỗi bị nuốt vào một dòng `error:` chung nên trang hiện "Vui lòng đăng nhập"
 * kể cả khi đã đăng nhập, và không ai phân biệt được hai ca đó.
 */
@Component({
  selector: 'app-alerts',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './alerts.component.html',
})
export class AlertsComponent implements OnInit {
  alerts: PriceAlert[] = [];
  dangTai = true;
  /** Chưa đăng nhập — khác hẳn lỗi tải, nên giao diện mời đăng nhập thay vì
   *  báo hỏng. Phân biệt bằng 401 chứ không đoán. */
  canDangNhap = false;
  loi: string | null = null;

  constructor(
    private alertService: AlertService,
    private authService: AuthService,
  ) {}

  ngOnInit(): void {
    this.tai();
  }

  tai(): void {
    // Không có token thì khỏi gọi: chắc chắn 401, mà một vòng mạng chỉ để nhận
    // câu trả lời đã biết trước thì chỉ làm trang chớp một nhịp.
    if (!this.authService.isLoggedIn()) {
      this.canDangNhap = true;
      this.dangTai = false;
      return;
    }

    this.dangTai = true;
    this.loi = null;
    this.alertService.getAlerts().subscribe({
      next: (res) => {
        this.alerts = res.alerts;
        this.dangTai = false;
      },
      error: (err) => {
        this.dangTai = false;
        if (err.status === 401) {
          this.canDangNhap = true;
          return;
        }
        this.loi = 'Không tải được danh sách cảnh báo. Thử lại sau ít phút.';
      },
    });
  }

  xoa(alert: PriceAlert): void {
    this.alertService.deleteAlert(alert.id).subscribe({
      // Lọc theo `id` của cảnh báo, không theo `game_id`: một game có thể có
      // nhiều cảnh báo ở các mức giá khác nhau, lọc theo game sẽ xoá nhầm cả
      // những cái còn sống trên màn hình.
      next: () => {
        this.alerts = this.alerts.filter((a) => a.id !== alert.id);
      },
      error: () => {
        this.loi = 'Không xoá được cảnh báo. Thử lại sau.';
      },
    });
  }

  /** `value` lưu theo đơn vị tiền, hiển thị theo locale Việt. */
  dinhDangGia(alert: PriceAlert): string {
    if (alert.value === null) {
      return '—';
    }
    return `${alert.value.toLocaleString('vi-VN')} ${alert.currency}`;
  }
}
