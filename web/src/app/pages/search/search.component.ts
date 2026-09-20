import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { Subscription } from 'rxjs';
import { SearchService, SearchHit, SearchResponse } from '../../services/search.service';

@Component({
  selector: 'app-search',
  standalone: true,
  imports: [CommonModule, RouterLink, FormsModule],
  templateUrl: './search.component.html',
  styleUrls: ['./search.component.css']
})
export class SearchComponent implements OnInit, OnDestroy {
  query = '';
  platform = '';
  genre = '';
  year: number | null = null;
  
  page = 1;
  limit = 20;
  
  isLoading = false;
  error = '';
  
  response: SearchResponse | null = null;
  hits: SearchHit[] = [];

  readonly PLATFORMS = ['android', 'ios', 'pc', 'ps4', 'ps5', 'switch', 'xbox-one', 'xbox-series'];
  readonly GENRES = [
    'accounting', 'action', 'action-adventure', 'action-rpg', 'adventure', 'animation-modeling',
    'audio-production', 'battle-royale', 'board', 'books', 'business', 'card', 'casino', 'casual',
    'crpg', 'design-illustration', 'early-access', 'education', 'family', 'food-drink', 'fps',
    'free-to-play', 'gacha', 'game-development', 'gore', 'graphics-design', 'health-fitness',
    'indie', 'jrpg', 'lifestyle', 'massively-multiplayer', 'metroidvania', 'mmorpg', 'moba',
    'movie', 'music', 'news', 'nudity', 'photo-editing', 'puzzle', 'racing', 'role-playing',
    'rpg', 'rts', 'sandbox', 'sexual-content', 'shopping', 'simulation', 'social-networking',
    'software-training', 'sports', 'strategy', 'travel', 'trivia', 'utilities', 'video-production',
    'violent', 'weather', 'word'
  ];

  private sub?: Subscription;

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private searchService: SearchService
  ) {}

  ngOnInit(): void {
    this.sub = this.route.queryParams.subscribe(params => {
      this.query = params['q'] || '';
      this.platform = params['platform'] || '';
      this.genre = params['genre'] || '';
      this.year = params['year'] ? Number(params['year']) : null;
      this.page = Number(params['page']) || 1;
      this.doSearch();
    });
  }

  ngOnDestroy(): void {
    if (this.sub) {
      this.sub.unsubscribe();
    }
  }

  onFilterChange(): void {
    this.router.navigate(['/search'], {
      queryParams: {
        q: this.query || undefined,
        platform: this.platform || undefined,
        genre: this.genre || undefined,
        year: this.year || undefined,
        page: 1
      }
    });
  }

  doSearch(): void {
    if (!this.query.trim() && !this.platform && !this.genre && !this.year) {
      this.hits = [];
      this.response = null;
      return;
    }

    this.isLoading = true;
    this.error = '';

    this.searchService.search(this.query, this.page, this.limit, this.platform || undefined, this.genre || undefined, this.year || undefined).subscribe({
      next: (res) => {
        this.response = res;
        this.hits = res.hits;
        this.isLoading = false;
      },
      error: (err) => {
        console.error('Lỗi khi tìm kiếm:', err);
        this.error = 'Không thể tải kết quả tìm kiếm. Vui lòng thử lại sau.';
        this.isLoading = false;
      }
    });
  }
}
