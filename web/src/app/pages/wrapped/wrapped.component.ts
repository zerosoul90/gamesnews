import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { UserService, WrappedData } from '../../services/user.service';

@Component({
  selector: 'app-wrapped',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './wrapped.component.html',
})
export class WrappedComponent implements OnInit {
  wrappedData: WrappedData | null = null;
  isLoading = true;
  error: string | null = null;
  currentYear = new Date().getFullYear();

  constructor(private userService: UserService) {}

  ngOnInit(): void {
    this.loadWrapped(this.currentYear);
  }

  loadWrapped(year: number): void {
    this.isLoading = true;
    this.error = null;
    this.userService.getWrapped(year).subscribe({
      next: (data) => {
        this.wrappedData = data;
        this.isLoading = false;
      },
      error: (err) => {
        this.error = 'Không thể tải dữ liệu Wrapped. Vui lòng thử lại sau.';
        this.isLoading = false;
      }
    });
  }
}
