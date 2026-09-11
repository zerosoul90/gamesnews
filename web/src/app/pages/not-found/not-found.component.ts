import { Component, Inject, OnDestroy, OnInit, Optional } from '@angular/core';
import { Meta, Title } from '@angular/platform-browser';
import { RouterLink } from '@angular/router';

import { RENDER_STATUS, RenderStatus } from '../../render-status';

@Component({
  selector: 'app-not-found',
  standalone: true,
  imports: [RouterLink],
  templateUrl: './not-found.component.html',
})
export class NotFoundComponent implements OnInit, OnDestroy {
  constructor(
    private titleService: Title,
    private metaService: Meta,
    // Đặt status ngay trong constructor, không đợi ngOnInit: cả hai đều chạy
    // xong trước khi `render()` resolve, nhưng constructor là chỗ chắc chắn
    // chạy đúng một lần cho mỗi lần dựng component.
    @Optional() @Inject(RENDER_STATUS) renderStatus: RenderStatus | null,
  ) {
    if (renderStatus) {
      renderStatus.statusCode = 404;
    }
  }

  ngOnInit(): void {
    this.titleService.setTitle('Không tìm thấy trang - GameNews');
    // `noindex` mới là phần quan trọng: trước đây mọi URL rác đều trả 200 kèm
    // vỏ app rỗng, nên bot index được vô số trang trắng trùng nội dung.
    this.metaService.updateTag({ name: 'robots', content: 'noindex' });
  }

  ngOnDestroy(): void {
    // Angular không tự dọn meta tag khi rời trang. Bỏ qua bước này thì điều
    // hướng 404 -> /deals trong app để lại `noindex` trên một trang cần index.
    this.metaService.removeTag("name='robots'");
  }
}
