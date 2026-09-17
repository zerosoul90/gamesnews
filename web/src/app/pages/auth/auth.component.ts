import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router, ActivatedRoute, RouterLink } from '@angular/router';
import { AuthService } from '../../services/auth.service';

@Component({
  selector: 'app-auth',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink],
  templateUrl: './auth.component.html',
})
export class AuthComponent implements OnInit {
  isLoginMode = true;
  isLoading = false;
  error: string | null = null;

  email = '';
  password = '';
  username = ''; // For registration

  constructor(
    private authService: AuthService,
    private router: Router,
    private route: ActivatedRoute
  ) {}

  ngOnInit(): void {
    // Determine mode from route data or URL
    const url = this.router.url;
    if (url.includes('register')) {
      this.isLoginMode = false;
    }
  }

  toggleMode(): void {
    this.isLoginMode = !this.isLoginMode;
    this.error = null;
  }

  onSubmit(): void {
    if (!this.email || !this.password || (!this.isLoginMode && !this.username)) {
      this.error = 'Vui lòng điền đầy đủ thông tin.';
      return;
    }

    this.isLoading = true;
    this.error = null;

    if (this.isLoginMode) {
      this.authService.login({ email: this.email, password: this.password }).subscribe({
        next: () => {
          this.isLoading = false;
          this.router.navigate(['/']);
        },
        error: (err) => {
          this.isLoading = false;
          this.error = err.error?.detail || 'Đăng nhập thất bại. Vui lòng kiểm tra lại thông tin.';
        }
      });
    } else {
      this.authService.register({ email: this.email, password: this.password, username: this.username }).subscribe({
        next: () => {
          this.isLoading = false;
          this.router.navigate(['/']);
        },
        error: (err) => {
          this.isLoading = false;
          this.error = err.error?.detail || 'Đăng ký thất bại. Email có thể đã được sử dụng.';
        }
      });
    }
  }
}
