import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { Meta, Title } from '@angular/platform-browser';

import { ForumService, ChuyenMuc } from '../../services/forum.service';
import { ForumTrangThaiComponent } from '../../components/forum-trang-thai/forum-trang-thai.component';

/** `/forum` — danh sách chuyên mục chung.
 *
 *  Khu thảo luận theo từng game không liệt kê ở đây (hơn 40.000 game); nó
 *  nằm trên trang của chính game đó — chặng F3 ở `docs/FORUM.md`. */
@Component({
  selector: 'app-forum-home',
  standalone: true,
  imports: [CommonModule, RouterLink, ForumTrangThaiComponent],
  templateUrl: './forum-home.component.html',
})
export class ForumHomeComponent implements OnInit {
  chuyenMuc: ChuyenMuc[] = [];
  dangTai = true;
  loi: string | null = null;

  constructor(
    private forum: ForumService,
    private title: Title,
    private meta: Meta,
  ) {}

  ngOnInit(): void {
    this.title.setTitle('Diễn đàn - GameNews');
    this.meta.updateTag({
      name: 'description',
      content: 'Diễn đàn trao đổi về game: thảo luận, hỏi đáp, tìm đồng đội, chia sẻ deal.',
    });
    this.tai();
  }

  tai(): void {
    this.dangTai = true;
    this.loi = null;
    this.forum.chuyenMuc().subscribe({
      next: (ds) => {
        this.chuyenMuc = ds;
        this.dangTai = false;
      },
      error: () => {
        this.loi = 'Không tải được danh sách chuyên mục.';
        this.dangTai = false;
      },
    });
  }
}
