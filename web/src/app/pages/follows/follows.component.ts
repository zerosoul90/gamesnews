import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { UserService } from '../../services/user.service';
import { Article } from '../../services/news.service';

@Component({
  selector: 'app-follows',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './follows.component.html',
})
export class FollowsComponent implements OnInit {
  articles: Article[] = [];
  isLoading = true;
  error: string | null = null;

  constructor(private userService: UserService) {}

  ngOnInit(): void {
    this.loadFeed();
  }

  loadFeed(): void {
    this.isLoading = true;
    this.error = null;
    this.userService.getFollowsFeed().subscribe({
      next: (res) => {
        this.articles = res.articles;
        this.isLoading = false;
      },
      error: (err) => {
        this.error = 'Không thể tải bảng tin. Vui lòng đăng nhập.';
        this.isLoading = false;
      }
    });
  }
}
