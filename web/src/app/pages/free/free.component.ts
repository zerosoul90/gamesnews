import { Component, OnInit } from '@angular/core';
import { Meta, Title } from '@angular/platform-browser';

@Component({
  selector: 'app-free',
  standalone: true,
  imports: [],
  templateUrl: './free.component.html',
  styleUrl: './free.component.css'
})
export class FreeComponent implements OnInit {
  constructor(private titleService: Title, private metaService: Meta) {}

  ngOnInit(): void {
    const pageTitle = "Game Miễn Phí Tuần Này - Nhận ngay kẻo lỡ!";
    const description = "Tổng hợp danh sách các tựa game đang được phát hành miễn phí 100% trên Epic Games, Steam. Thêm vào thư viện ngay, chơi lúc nào tùy thích.";
    
    this.titleService.setTitle(pageTitle);
    this.metaService.updateTag({ name: 'description', content: description });
    this.metaService.updateTag({ property: 'og:title', content: pageTitle });
    this.metaService.updateTag({ property: 'og:description', content: description });
  }
}
