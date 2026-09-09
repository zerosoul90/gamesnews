import { Component, OnInit } from '@angular/core';
import { Meta, Title } from '@angular/platform-browser';
import { ActivatedRoute } from '@angular/router';

@Component({
  selector: 'app-game',
  standalone: true,
  imports: [],
  templateUrl: './game.component.html',
  styleUrl: './game.component.css'
})
export class GameComponent implements OnInit {
  
  constructor(
    private titleService: Title,
    private metaService: Meta,
    private route: ActivatedRoute
  ) {}

  ngOnInit(): void {
    // Giả lập fetch dữ liệu từ API dựa theo slug
    const slug = this.route.snapshot.paramMap.get('slug') || 'elden-ring';
    
    // SEO Meta Tags Dynamic Generation
    const gameName = "Elden Ring";
    const minPrice = "595.000₫";
    const description = `${gameName} giá rẻ nhất chỉ từ ${minPrice}. Kiểm tra cấu hình máy tính chơi ${gameName}, ngày ra mắt và đánh giá mới nhất.`;
    
    this.titleService.setTitle(`${gameName} - Giá mua, Cấu hình và Thông tin`);
    
    this.metaService.updateTag({ name: 'description', content: description });
    
    // Open Graph
    this.metaService.updateTag({ property: 'og:title', content: `${gameName} đang giảm giá sốc!` });
    this.metaService.updateTag({ property: 'og:description', content: description });
    // URL ảnh động từ backend API
    this.metaService.updateTag({ property: 'og:image', content: `https://gamenews.vn/api/v1/og-image?game=${slug}` });
    
    // Canonical link (cần thao tác DOM hoặc custom service, bỏ qua trong MVP)
  }
}
