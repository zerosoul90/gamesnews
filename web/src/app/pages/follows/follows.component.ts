import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';

import { UserService, Follow } from '../../services/user.service';
import { AuthService } from '../../services/auth.service';

/**
 * "Tôi đang theo dõi".
 *
 * Bản trước gọi `/me/follows` và đọc `res.articles`, tức chờ một *bảng tin*.
 * Backend không có bảng tin theo dõi: `/api/v1/user/follows` trả về danh sách
 * những thứ đang được theo dõi (`{follows, total}`). Kể cả khi endpoint kia có
 * thật thì trường `articles` vẫn luôn `undefined`.
 */
@Component({
  selector: 'app-follows',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './follows.component.html',
})
export class FollowsComponent implements OnInit {
  follows: Follow[] = [];
  dangTai = true;
  canDangNhap = false;
  loi: string | null = null;

  constructor(
    private userService: UserService,
    private authService: AuthService,
  ) {}

  ngOnInit(): void {
    this.tai();
  }

  tai(): void {
    if (!this.authService.isLoggedIn()) {
      this.canDangNhap = true;
      this.dangTai = false;
      return;
    }

    this.dangTai = true;
    this.loi = null;
    this.userService.getFollows().subscribe({
      next: (res) => {
        this.follows = res.follows;
        this.dangTai = false;
      },
      error: (err) => {
        this.dangTai = false;
        if (err.status === 401) {
          this.canDangNhap = true;
          return;
        }
        this.loi = 'Không tải được danh sách theo dõi. Thử lại sau ít phút.';
      },
    });
  }

  boTheoDoi(follow: Follow): void {
    this.userService.unfollow(follow.id).subscribe({
      next: () => {
        this.follows = this.follows.filter((f) => f.id !== follow.id);
      },
      error: () => {
        this.loi = 'Không bỏ theo dõi được. Thử lại sau.';
      },
    });
  }

  /** Nhãn tiếng Việt cho `target_type`. Mục lạ thì trả nguyên chuỗi gốc chứ
   *  không nuốt thành "Khác" — nuốt đi là mất manh mối khi thêm loại mới. */
  nhanLoai(loai: string): string {
    const bang: Record<string, string> = {
      game: 'Game',
      series: 'Series',
      developer: 'Studio',
      streamer: 'Streamer',
    };
    return bang[loai] ?? loai;
  }
}
