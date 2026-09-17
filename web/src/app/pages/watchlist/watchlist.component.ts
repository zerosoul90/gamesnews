import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { WatchlistService, WatchlistItem } from '../../services/watchlist.service';

@Component({
  selector: 'app-watchlist',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './watchlist.component.html',
})
export class WatchlistComponent implements OnInit {
  items: WatchlistItem[] = [];
  isLoading = true;
  error: string | null = null;

  constructor(private watchlistService: WatchlistService) {}

  ngOnInit(): void {
    this.loadWatchlist();
  }

  loadWatchlist(): void {
    this.isLoading = true;
    this.error = null;
    this.watchlistService.getWatchlist().subscribe({
      next: (res) => {
        this.items = res.items;
        this.isLoading = false;
      },
      error: (err) => {
        this.error = 'Không thể tải danh sách theo dõi. Vui lòng đăng nhập.';
        this.isLoading = false;
      }
    });
  }

  removeItem(gameId: string): void {
    this.watchlistService.removeFromWatchlist(gameId).subscribe({
      next: () => {
        this.items = this.items.filter(item => item.game_id !== gameId);
      },
      error: () => {
        alert('Lỗi khi xoá khỏi danh sách theo dõi');
      }
    });
  }
}
