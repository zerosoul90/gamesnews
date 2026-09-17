import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router, RouterLink, RouterLinkActive } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { Subscription } from 'rxjs';

import { AuthService, User } from '../../services/auth.service';

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
  currentUser: User | null = null;
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
    this.router.navigate(['/login']);
  }

  /** Một nguồn sự thật cho danh sách mục, để thêm trang sau này không phải sửa
   *  cả bản desktop lẫn bản mobile của cùng một danh sách. */
  readonly muc = [
    { duongDan: '/deals', nhan: 'Deal' },
    { duongDan: '/free', nhan: 'Miễn phí' },
    { duongDan: '/news', nhan: 'Tin tức' },
    { duongDan: '/thong-ke', nhan: 'Thống kê' },
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
