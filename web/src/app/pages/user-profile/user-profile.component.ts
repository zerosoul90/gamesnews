import { Component, OnDestroy, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { Subscription } from 'rxjs';

import { AuthService, SteamSession } from '../../services/auth.service';

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

  constructor(private authService: AuthService) {}

  ngOnInit(): void {
    this.sub = this.authService.currentUser$.subscribe((p) => (this.phien = p));
  }

  ngOnDestroy(): void {
    this.sub?.unsubscribe();
  }
}
