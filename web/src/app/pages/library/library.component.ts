import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';

import { UserService, LibraryItem } from '../../services/user.service';
import { AuthService } from '../../services/auth.service';

@Component({
  selector: 'app-library',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './library.component.html',
})
export class LibraryComponent implements OnInit {
  items: LibraryItem[] = [];
  total = 0;
  dangTai = true;
  canDangNhap = false;
  loi: string | null = null;
  loiPrivateProfile = false;
  dangDongBo = false;
  dongBoKetQua: { synced: number; skipped: number } | null = null;
  dangXoa = false;

  constructor(
    private userService: UserService,
    public authService: AuthService,
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
    this.loiPrivateProfile = false;
    this.dongBoKetQua = null;

    this.userService.getLibrary(50, 0).subscribe({
      next: (res) => {
        this.items = res.items;
        this.total = res.total;
        this.dangTai = false;
      },
      error: (err) => {
        this.dangTai = false;
        if (err.status === 401) {
          this.canDangNhap = true;
          return;
        }
        this.loi = 'Không tải được thư viện. Thử lại sau ít phút.';
      },
    });
  }

  dongBo(): void {
    this.dangDongBo = true;
    this.loi = null;
    this.loiPrivateProfile = false;
    this.dongBoKetQua = null;

    this.userService.syncLibrary().subscribe({
      next: (res) => {
        this.dangDongBo = false;
        this.dongBoKetQua = res;
        this.tai();
      },
      error: (err) => {
        this.dangDongBo = false;
        if (err.status === 403 && err.error?.detail === 'PROFILE_IS_PRIVATE') {
          this.loiPrivateProfile = true;
        } else {
          this.loi = 'Lỗi đồng bộ. Thử lại sau.';
        }
      }
    });
  }

  xoaThuVien(): void {
    if (!confirm('Bạn có chắc chắn muốn xoá toàn bộ thư viện game đã lưu? Hành động này không thể hoàn tác.')) {
      return;
    }
    this.dangXoa = true;
    this.loi = null;
    this.userService.deleteLibrary().subscribe({
      next: () => {
        this.dangXoa = false;
        this.items = [];
        this.total = 0;
      },
      error: () => {
        this.dangXoa = false;
        this.loi = 'Lỗi xoá thư viện. Thử lại sau.';
      }
    });
  }
}
