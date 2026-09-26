import { Component, EventEmitter, OnInit, Output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';

import { AuthService } from '../../services/auth.service';
import { ForumService, TrangThaiDang, cauBaoLoi } from '../../services/forum.service';

/**
 * Ô "bạn đang là ai trên diễn đàn", đặt đầu cả ba trang diễn đàn.
 *
 * Bốn trạng thái, theo đúng thứ tự cổng ở backend (`docs/FORUM.md`):
 * chưa đăng nhập → chưa có biệt danh → chưa được cấp quyền beta → đăng được.
 *
 * Lý do "chưa đăng được" lấy nguyên văn từ `GET /forum/me`, không tự suy ra ở
 * đây: suy ra ở hai nơi thì sớm muộn hai nơi nói khác nhau, và người dùng thấy
 * nút đăng bài rồi bấm vào nhận 403.
 */
@Component({
  selector: 'app-forum-trang-thai',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink],
  templateUrl: './forum-trang-thai.component.html',
})
export class ForumTrangThaiComponent implements OnInit {
  /** Trang cha dùng để quyết định có hiện form đăng bài hay không. */
  @Output() doiTrangThai = new EventEmitter<TrangThaiDang | null>();

  trangThai: TrangThaiDang | null = null;
  daDangNhap = false;
  bietDanh = '';
  dangGui = false;
  loi: string | null = null;
  /** Người đã có biệt danh bấm "đổi" thì mới mở lại form. */
  dangDoi = false;

  constructor(
    private forum: ForumService,
    private auth: AuthService,
  ) {}

  ngOnInit(): void {
    this.daDangNhap = this.auth.isLoggedIn();
    if (!this.daDangNhap) {
      this.doiTrangThai.emit(null);
      return;
    }
    this.forum.trangThai().subscribe({
      next: (t) => this.gan(t),
      // Không tải được trạng thái thì coi như chưa đăng được — an toàn hơn
      // là hiện nút đăng bài rồi để backend từ chối.
      error: (err) => {
        this.loi = cauBaoLoi(err, 'Không tải được trạng thái tài khoản diễn đàn.');
        this.doiTrangThai.emit(null);
      },
    });
  }

  get hienForm(): boolean {
    return this.trangThai !== null && (!this.trangThai.nickname || this.dangDoi);
  }

  moDoi(): void {
    this.dangDoi = true;
    this.bietDanh = this.trangThai?.nickname ?? '';
    this.loi = null;
  }

  luuBietDanh(): void {
    if (this.dangGui || !this.bietDanh.trim()) {
      return;
    }
    this.dangGui = true;
    this.loi = null;
    this.forum.datBietDanh(this.bietDanh).subscribe({
      next: (t) => {
        this.dangGui = false;
        this.dangDoi = false;
        this.gan(t);
      },
      error: (err) => {
        this.dangGui = false;
        this.loi = cauBaoLoi(err);
      },
    });
  }

  private gan(t: TrangThaiDang): void {
    this.trangThai = t;
    this.doiTrangThai.emit(t);
  }
}
