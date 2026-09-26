import { Component, inject } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Meta } from '@angular/platform-browser';
import { ActivatedRoute, provideRouter } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';

import { provideMetaRobotsReset } from './meta-robots';

/** Đặt `noindex` ngay trong constructor, như trang đăng nhập. */
@Component({ selector: 'trang-1', standalone: true, template: '' })
class TrangNoindex {
  constructor() {
    inject(Meta).updateTag({ name: 'robots', content: 'noindex' });
  }
}

@Component({ selector: 'trang-2', standalone: true, template: '' })
class TrangThuong {}

/** Như trang game: cùng một component cho mọi slug, slug sai thì `noindex`. */
@Component({ selector: 'trang-3', standalone: true, template: '' })
class TrangGame {
  constructor() {
    const meta = inject(Meta);
    inject(ActivatedRoute).paramMap.subscribe((p) => {
      if (p.get('slug') === 'khong-co') {
        meta.updateTag({ name: 'robots', content: 'noindex' });
      }
    });
  }
}

describe('provideMetaRobotsReset', () => {
  let meta: Meta;
  let harness: RouterTestingHarness;

  const robots = () => meta.getTag("name='robots'")?.content ?? null;

  beforeEach(async () => {
    TestBed.configureTestingModule({
      providers: [
        provideRouter([
          { path: 'dang-nhap', component: TrangNoindex },
          { path: 'deals', component: TrangThuong },
          { path: 'game/:slug', component: TrangGame },
        ]),
        provideMetaRobotsReset(),
      ],
    });
    meta = TestBed.inject(Meta);
    meta.removeTag("name='robots'");
    harness = await RouterTestingHarness.create();
  });

  afterEach(() => meta.removeTag("name='robots'"));

  it('rời trang noindex sang trang thường thì gỡ tag', async () => {
    await harness.navigateByUrl('/dang-nhap');
    expect(robots()).toBe('noindex');
    await harness.navigateByUrl('/deals');
    expect(robots()).toBeNull();
  });

  it('gỡ cả khi router tái sử dụng component (game 404 -> game thật)', async () => {
    await harness.navigateByUrl('/game/khong-co');
    expect(robots()).toBe('noindex');
    await harness.navigateByUrl('/game/portal-2');
    expect(robots()).toBeNull();
  });

  it('không xoá tag trang mới vừa đặt khi dựng', async () => {
    await harness.navigateByUrl('/deals');
    await harness.navigateByUrl('/dang-nhap');
    expect(robots()).toBe('noindex');
  });
});
