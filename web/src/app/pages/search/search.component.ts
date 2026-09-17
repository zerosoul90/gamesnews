import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { Subscription } from 'rxjs';
import { SearchService, SearchHit, SearchResponse } from '../../services/search.service';

@Component({
  selector: 'app-search',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './search.component.html',
  styleUrls: ['./search.component.css']
})
export class SearchComponent implements OnInit, OnDestroy {
  query = '';
  page = 1;
  limit = 20;
  
  isLoading = false;
  error = '';
  
  response: SearchResponse | null = null;
  hits: SearchHit[] = [];

  private sub?: Subscription;

  constructor(
    private route: ActivatedRoute,
    private searchService: SearchService
  ) {}

  ngOnInit(): void {
    this.sub = this.route.queryParams.subscribe(params => {
      this.query = params['q'] || '';
      this.page = Number(params['page']) || 1;
      this.doSearch();
    });
  }

  ngOnDestroy(): void {
    if (this.sub) {
      this.sub.unsubscribe();
    }
  }

  doSearch(): void {
    if (!this.query.trim()) {
      this.hits = [];
      this.response = null;
      return;
    }

    this.isLoading = true;
    this.error = '';

    this.searchService.search(this.query, this.page, this.limit).subscribe({
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
