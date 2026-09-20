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
  dangTaiThem = false;

  private readonly soMoiTrang = 50;

  /** Còn game chưa tải hay không.
   *
   * So `items.length` với `total` của API, không so độ dài trang vừa nhận với
   * `limit`: cách sau sai đúng ở ca trang cuối vừa tròn 50 — nó mời người dùng
   * bấm "tải thêm" một lần nữa để nhận về mảng rỗng. Cùng lý do đã ghi ở
   * `news.component.ts`.
   */
  get conNua(): boolean {
    return this.items.length < this.total;
  }

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
    // KHÔNG xoá `dongBoKetQua` ở đây. `dongBo()` gán kết quả rồi gọi ngay
    // `tai()` để nạp lại danh sách — đồng bộ, cùng một lượt — nên dòng reset
    // đặt ở đây nuốt mất băng rôn trước khi nó kịp hiện một lần nào. Ca
    // `{synced: 0, skipped: N}`, ca cần nói nhất, im hoàn toàn.
    // Việc dọn thuộc về lúc *bắt đầu* một lần đồng bộ mới, xem `dongBo()`.

    this.userService.getLibrary(this.soMoiTrang, 0).subscribe({
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

  /** Nạp trang tiếp theo và nối vào cuối danh sách.
   *
   * `offset` lấy từ `items.length` chứ không đếm số trang: hai cách chỉ khác
   * nhau khi một trang trả về thiếu, và khi đó đếm trang sẽ nhảy cóc qua vài
   * game mà không ai biết.
   *
   * Trước bản này trang chỉ gọi `getLibrary(50, 0)` đúng một lần: ai có hơn 50
   * game thì mất phần còn lại, im lặng — `total` vẫn nhận về nhưng không hiện
   * ở đâu, nên không có cả dấu hiệu nào cho thấy còn thiếu.
   */
  taiThem(): void {
    if (this.dangTaiThem || !this.conNua) {
      return;
    }
    this.dangTaiThem = true;
    this.loi = null;

    this.userService.getLibrary(this.soMoiTrang, this.items.length).subscribe({
      next: (res) => {
        this.items = [...this.items, ...res.items];
        this.total = res.total;
        this.dangTaiThem = false;
      },
      error: () => {
        this.dangTaiThem = false;
        // Giữ nguyên những gì đã tải được. Xoá sạch danh sách vì một trang
        // hỏng là phạt người dùng nặng hơn hẳn lỗi thật sự xảy ra.
        this.loi = 'Không tải thêm được. Thử lại sau ít phút.';
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
    // Xoá sạch thư viện thì băng rôn "đã đồng bộ N game" của lượt trước thành
    // lời nói dối; dọn nó cùng lúc với dữ liệu nó mô tả.
    this.dongBoKetQua = null;
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
