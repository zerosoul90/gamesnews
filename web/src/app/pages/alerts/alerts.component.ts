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

  /**
   * Câu mô tả điều kiện, viết trọn nghĩa.
   *
   * Bản trước ghép `'Báo khi giá ' + condition + ' ' + value` nên màn hình hiện
   * "Báo khi giá historical_low —": in thẳng tên hằng của backend, cộng một gạch
   * ngang thay cho `value` vốn **đúng** là `null` với điều kiện này. Người đọc
   * không suy ra được nó sẽ báo khi nào.
   */
  moTaDieuKien(alert: PriceAlert): string {
    switch (alert.condition) {
      case 'historical_low':
        // Điều kiện này không có ngưỡng — `value` luôn null, và đó là đúng.
        return 'Báo khi giá chạm đáy lịch sử';
      case 'below_price':
        return alert.value === null
          ? 'Báo khi giá giảm'
          : `Báo khi giá dưới ${alert.value.toLocaleString('vi-VN')} ${alert.currency}`;
      case 'discount_pct':
        return alert.value === null
          ? 'Báo khi có giảm giá'
          : `Báo khi giảm từ ${alert.value}%`;
      default:
        // Điều kiện lạ: hiện nguyên chuỗi thay vì nuốt thành câu chung chung —
        // nuốt đi là mất manh mối khi backend thêm loại mới.
        return `Báo khi: ${alert.condition}`;
    }
  }
}
