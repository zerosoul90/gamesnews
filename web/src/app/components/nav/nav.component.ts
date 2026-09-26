import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router, RouterLink, RouterLinkActive } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { Subscription } from 'rxjs';

import { AuthService, SteamSession } from '../../services/auth.service';

/**
 * Thanh điều hướng chung.
 */
@Component({
  selector: 'app-nav',
  standalone: true,
  imports: [CommonModule, RouterLink, RouterLinkActive, FormsModule],
  templateUrl: './nav.component.html',
})
export class NavComponent implements OnInit, OnDestroy {
  searchQuery = '';
  currentUser: SteamSession | null = null;
  private authSub?: Subscription;

  constructor(
    private router: Router,
    private authService: AuthService
  ) {}

  ngOnInit(): void {
    this.authSub = this.authService.currentUser$.subscribe(user => {
      this.currentUser = user;
    });
  }

  ngOnDestroy(): void {
    this.authSub?.unsubscribe();
  }

  logout(): void {
    this.authService.logout();
    this.router.navigate(['/']);
  }

  /** Một nguồn sự thật cho danh sách mục, để thêm trang sau này không phải sửa
   *  cả bản desktop lẫn bản mobile của cùng một danh sách. */
  readonly muc = [
    { duongDan: '/deals', nhan: 'Deal' },
    { duongDan: '/free', nhan: 'Miễn phí' },
    { duongDan: '/news', nhan: 'Tin tức' },
    { duongDan: '/forum', nhan: 'Diễn đàn' },
    { duongDan: '/thong-ke', nhan: 'Thống kê' },
  ];

  /** Mục chỉ hiện khi đã đăng nhập. Tách khỏi `muc` vì ba trang này đòi token;
   *  để lẫn vào menu chung thì khách vãng lai bấm vào chỉ gặp lời mời đăng
   *  nhập. Trước đây chúng không nằm trong nav nào — không gõ tay URL thì
   *  không tới được, đúng lỗi mà `/free` đã mắc ở lượt 10. */
  readonly mucCaNhan = [
    { duongDan: '/canh-bao-gia', nhan: 'Cảnh báo giá' },
    { duongDan: '/follows', nhan: 'Đang theo dõi' },
    { duongDan: '/thu-vien', nhan: 'Thư viện' },
    { duongDan: '/wrapped', nhan: 'Wrapped' },
    { duongDan: '/cai-dat-thong-bao', nhan: 'Thông báo' },
  ];

  dangMoMobile = false;

  doiMenuMobile(): void {
    this.dangMoMobile = !this.dangMoMobile;
  }

  dongMenuMobile(): void {
    this.dangMoMobile = false;
  }

  onSearch(): void {
    if (this.searchQuery.trim()) {
      this.router.navigate(['/search'], { queryParams: { q: this.searchQuery.trim() } });
      this.dongMenuMobile();
      this.searchQuery = '';
    }
  }
}
