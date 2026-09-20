import { Component, OnDestroy, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { Subscription } from 'rxjs';

import { AuthService, SteamSession } from '../../services/auth.service';
import { LyDoKhongBat, PushService } from '../../services/push.service';
import { CommunityService, Badge } from '../../services/community.service';

/**
 * Trang cá nhân.
 *
 * Chỉ hiển thị những gì hệ thống thật sự biết: SteamID. Bản trước in
 * `username`, `email` và `created_at` — không trường nào tồn tại, nên trang
 * hiện tên trống và "Thành viên từ" bỏ lửng.
 */
@Component({
  selector: 'app-user-profile',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './user-profile.component.html',
})
export class UserProfileComponent implements OnInit, OnDestroy {
  phien: SteamSession | null = null;
  private sub?: Subscription;

  // --- push ---
  dangBatPush = false;
  daBatPush = false;
  loiPush: string | null = null;

  constructor(
    private authService: AuthService,
    public pushService: PushService,
    private communityService: CommunityService,
  ) {}

  badges: Badge[] = [];
  dangTaiBadges = false;

  ngOnInit(): void {
    this.sub = this.authService.currentUser$.subscribe((p) => {
      this.phien = p;
      if (this.phien) {
        this.taiBadges(this.phien.user_id);
      } else {
        this.badges = [];
      }
    });
  }

  private taiBadges(userId: string): void {
    this.dangTaiBadges = true;
    this.communityService.getBadges(userId).subscribe({
      next: (badges) => {
        this.badges = badges;
        this.dangTaiBadges = false;
      },
      error: () => {
        this.dangTaiBadges = false;
      }
    });
  }

  ngOnDestroy(): void {
    this.sub?.unsubscribe();
  }

  async batThongBao(): Promise<void> {
    this.dangBatPush = true;
    this.loiPush = null;
    try {
      const ket_qua = await this.pushService.dangKyThietBi();
      if (ket_qua.ok) {
        this.daBatPush = true;
      } else {
        this.loiPush = this.moTaLyDo(ket_qua.lyDo);
      }
    } catch {
      // Lỗi mạng hoặc Firebase từ chối. Nói là chưa bật được, đừng để nút quay
      // về trạng thái ban đầu như thể chưa ai bấm.
      this.loiPush = 'Không bật được thông báo. Thử lại sau.';
    } finally {
      this.dangBatPush = false;
    }
  }

  /** Bốn lý do, bốn hành động khác nhau — gộp thành một câu là bỏ rơi người
   *  dùng ở ba trong bốn ca. */
  moTaLyDo(lyDo: LyDoKhongBat): string {
    switch (lyDo) {
      case 'chua-cau-hinh':
        return 'Máy chủ chưa cấu hình dịch vụ thông báo. Đây là việc của người quản trị, không phải của bạn.';
      case 'trinh-duyet-khong-ho-tro':
        return 'Trình duyệt này không hỗ trợ thông báo đẩy.';
      case 'bi-tu-choi':
        return 'Bạn đã chặn thông báo cho trang này. Mở cài đặt trang trong trình duyệt để bật lại.';
      default:
        return 'Không bật được thông báo.';
    }
  }
}
