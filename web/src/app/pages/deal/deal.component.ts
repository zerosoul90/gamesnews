import { Component, OnInit } from '@angular/core';
import { Meta, Title } from '@angular/platform-browser';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { DealService, Deal } from '../../services/deal.service';

@Component({
  selector: 'app-deal',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './deal.component.html',
  styleUrl: './deal.component.css'
})
export class DealComponent implements OnInit {
  deals: Deal[] = [];
  isLoading = true;
  filterBy = 'worth_buying';

  constructor(
    private titleService: Title, 
    private metaService: Meta,
    private dealService: DealService
  ) {}

  ngOnInit(): void {
    const pageTitle = "Deal Game Hot - Khuyến mãi game PC bản quyền";
    const description = "Tổng hợp danh sách deal game PC bản quyền giảm giá sâu nhất từ Steam, Epic Games. Mua game giá rẻ, tiết kiệm túi tiền.";
    
    this.titleService.setTitle(pageTitle);
    this.metaService.updateTag({ name: 'description', content: description });
    this.metaService.updateTag({ property: 'og:title', content: pageTitle });
    this.metaService.updateTag({ property: 'og:description', content: description });

    this.fetchDeals();
  }

  fetchDeals(): void {
    this.isLoading = true;
    this.dealService.getDeals(20, this.filterBy).subscribe({
      next: (res) => {
        this.deals = res.deals || [];
        this.isLoading = false;
      },
      error: (err) => {
        console.error('Lỗi khi lấy danh sách deal:', err);
        this.isLoading = false;
      }
    });
  }

  onFilterChange(event: Event): void {
    const selectElem = event.target as HTMLSelectElement;
    this.filterBy = selectElem.value;
    this.fetchDeals();
  }
}
