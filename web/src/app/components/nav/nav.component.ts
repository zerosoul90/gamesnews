import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink, RouterLinkActive } from '@angular/router';

/**
 * Thanh điều hướng chung.
 *
 * Trước component này `app.component.html` chỉ có đúng `<router-outlet>`: không
 * header, không nav, không footer. Hậu quả là `/free` và `/news` **không thể tới
 * được** trừ khi gõ tay URL — người dùng mở trang chủ chỉ thấy danh sách deal và
 * không có đường nào đi tiếp. Phase 4 đặt mục tiêu "web dùng được đầy đủ mà
 * không bắt cài app", và mục tiêu đó không thể đạt nếu không có nav.
 *
 * `RouterLinkActive` để người dùng biết mình đang ở đâu; thiếu nó thì ba mục
 * trông giống hệt nhau trên mọi trang.
 */
@Component({
  selector: 'app-nav',
  standalone: true,
  imports: [CommonModule, RouterLink, RouterLinkActive],
  templateUrl: './nav.component.html',
})
export class NavComponent {
  /** Một nguồn sự thật cho danh sách mục, để thêm trang sau này không phải sửa
   *  cả bản desktop lẫn bản mobile của cùng một danh sách. */
  readonly muc = [
    { duongDan: '/deals', nhan: 'Deal' },
    { duongDan: '/free', nhan: 'Miễn phí' },
    { duongDan: '/news', nhan: 'Tin tức' },
  ];

  dangMoMobile = false;

  doiMenuMobile(): void {
    this.dangMoMobile = !this.dangMoMobile;
  }

  dongMenuMobile(): void {
    this.dangMoMobile = false;
  }
}
