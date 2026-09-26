import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router, RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';

import { DealService, Deal, FreeGame } from '../../services/deal.service';
import { NewsService, Article } from '../../services/news.service';
import { HotGame, HotService } from '../../services/hot.service';

@Component({
  selector: 'app-home',
  standalone: true,
  imports: [CommonModule, RouterLink, FormsModule],
  templateUrl: './home.component.html',
})
export class HomeComponent implements OnInit {
  searchQuery = '';

  historicalDeals: Deal[] = [];
  freeGames: FreeGame[] = [];
  latestNews: Article[] = [];
  hotGames: HotGame[] = [];

  isLoadingDeals = true;
  isLoadingFreeGames = true;
  isLoadingNews = true;
  isLoadingHot = true;

  constructor(
    private router: Router,
    private dealService: DealService,
    private newsService: NewsService,
    private hotService: HotService,
  ) {}

  ngOnInit(): void {
    // 3-4 deal đáy lịch sử
    this.dealService.getDeals(4, 'historical_low').subscribe({
      next: (res) => {
        this.historicalDeals = res.deals;
        this.isLoadingDeals = false;
      },
      error: () => this.isLoadingDeals = false
    });

    // Game miễn phí
    this.dealService.getFreeGames(4).subscribe({
      next: (res) => {
        this.freeGames = res.free_games || [];
        this.isLoadingFreeGames = false;
      },
      error: () => this.isLoadingFreeGames = false
    });

    // 5 game đông người chơi nhất
    this.hotService.getHot('popular', 5).subscribe({
      next: (res) => {
        this.hotGames = res.games;
        this.isLoadingHot = false;
      },
      error: () => this.isLoadingHot = false
    });

    // 5 tin mới nhất
    this.newsService.getNews(5).subscribe({
      next: (res) => {
        this.latestNews = res.articles;
        this.isLoadingNews = false;
      },
      error: () => this.isLoadingNews = false
    });
  }

  onSearch(): void {
    if (this.searchQuery.trim()) {
      this.router.navigate(['/search'], { queryParams: { q: this.searchQuery.trim() } });
    }
  }
}
