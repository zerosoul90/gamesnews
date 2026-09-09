import { Component, OnInit } from '@angular/core';
import { Meta, Title } from '@angular/platform-browser';

@Component({
  selector: 'app-deal',
  standalone: true,
  imports: [],
  templateUrl: './deal.component.html',
  styleUrl: './deal.component.css'
})
export class DealComponent implements OnInit {
  constructor(private titleService: Title, private metaService: Meta) {}

  ngOnInit(): void {
    const pageTitle = "Deal Game Hot - Khuyến mãi game PC bản quyền";
    const description = "Tổng hợp danh sách deal game PC bản quyền giảm giá sâu nhất từ Steam, Epic Games. Mua game giá rẻ, tiết kiệm túi tiền.";
    
    this.titleService.setTitle(pageTitle);
    this.metaService.updateTag({ name: 'description', content: description });
    this.metaService.updateTag({ property: 'og:title', content: pageTitle });
    this.metaService.updateTag({ property: 'og:description', content: description });
  }
}
