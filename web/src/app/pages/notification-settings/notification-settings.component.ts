import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { Title } from '@angular/platform-browser';

import { AuthService } from '../../services/auth.service';
import { CaiDatThongBao, UserService } from '../../services/user.service';

/** Một công tắc: khoá trong `channels`, nhãn, và nó ảnh hưởng tới cái gì. */
interface CongTac {
  khoa: 'price_alert' | 'streamer_live' | 'forum_reply';
  nhan: string;
  moTa: string;
}

/**
 * `/cai-dat-thong-bao` — bật/tắt từng kênh, tần suất bản tin, giờ im lặng.
 *
 * Mỗi công tắc ở đây đều đã được kiểm là có tác dụng thật ở backend. Hai cái
 * từng KHÔNG có: `streamer_live` (gatekeeper không đọc) và tần suất bản tin (job
 * digest gửi mỗi ngày cho mọi người). Sửa cả hai trước khi làm trang này — một
 * công tắc không làm gì còn tệ hơn không có công tắc.
 *
 * Lưu một lần bằng nút, không lưu theo từng cú bấm: PUT thay cả khối cài đặt,
 * lưu từng cú bấm thì hai lần bấm nhanh có thể về tới server lệch thứ tự.
 */
@Component({
  selector: 'app-notification-settings',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink],
  templateUrl: './notification-settings.component.html',
})
export class NotificationSettingsComponent implements OnInit {
  readonly congTac: CongTac[] = [
    { khoa: 'price_alert', nhan: 'Cảnh báo giá', moTa: 'Khi game bạn đặt cảnh báo chạm ngưỡng giá.' },
    { khoa: 'streamer_live', nhan: 'Streamer lên sóng', moTa: 'Khi streamer bạn theo dõi bắt đầu live.' },
    {
      khoa: 'forum_reply',
      nhan: 'Trả lời trên diễn đàn',
      moTa: 'Khi có người trả lời chủ đề hoặc trích dẫn bài của bạn. Luôn gom vào bản tin, không báo ngay.',
    },
  ];

  caiDat: CaiDatThongBao | null = null;
  canDangNhap = false;
  dangTai = true;
  dangLuu = false;
  loi: string | null = null;
  daLuu = false;

  constructor(
    private users: UserService,
    private auth: AuthService,
    private title: Title,
  ) {}

  ngOnInit(): void {
    this.title.setTitle('Cài đặt thông báo - GameNews');
    if (!this.auth.isLoggedIn()) {
      this.canDangNhap = true;
      this.dangTai = false;
      return;
    }
    this.users.getNotificationSettings().subscribe({
      next: (c) => {
        this.caiDat = c;
        this.dangTai = false;
      },
      error: (err) => {
        this.dangTai = false;
        if (err.status === 401) {
          this.canDangNhap = true;
          return;
        }
        this.loi = 'Không tải được cài đặt. Thử lại sau.';
      },
    });
  }

  /** Có sửa gì thì ẩn dòng "đã lưu" — để nó không nói dối về trạng thái mới. */
  khiDoi(): void {
    this.daLuu = false;
  }

  luu(): void {
    if (!this.caiDat || this.dangLuu) {
      return;
    }
    this.dangLuu = true;
    this.loi = null;
    this.users.putNotificationSettings(this.caiDat).subscribe({
      next: (c) => {
        this.caiDat = c;
        this.dangLuu = false;
        this.daLuu = true;
      },
      error: (err) => {
        this.dangLuu = false;
        this.loi =
          err.status === 422
            ? 'Giờ im lặng phải có dạng HH:MM, ví dụ 22:00.'
            : 'Không lưu được. Thử lại sau.';
      },
    });
  }
}
