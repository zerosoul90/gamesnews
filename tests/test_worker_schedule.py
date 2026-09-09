"""Lịch chạy của worker — `app/jobs/worker.py`.

`WorkerSettings` trước đây **không có `cron_jobs`**. Worker khởi động sạch sẽ,
log "worker đã khởi động", rồi ngồi im mãi mãi: không job nào tự chạy, mọi thứ
phải enqueue bằng tay. Không có gì đỏ lên để nói ra điều đó — chính là kiểu
hỏng mà `PHASE-7.md` cảnh báo về job gia hạn WebSub ("quên thì thông báo im
lặng chết mà không báo lỗi").

Test này không kiểm giờ giấc cụ thể (đó là quyết định vận hành, sẽ còn chỉnh).
Nó kiểm hai thứ không được phép sai: **mọi job đều gọi được** và **mọi job cần
chạy định kỳ đều CÓ trong lịch**.
"""

from __future__ import annotations

from typing import Any, cast

from arq.worker import get_kwargs

from app.jobs.worker import WorkerSettings


def worker_kwargs() -> dict[str, Any]:
    """`arq.worker.get_kwargs` khai kiểu theo `WorkerSettingsBase`, mà dự án
    không kế thừa lớp đó (arq đọc thẳng `__dict__`). Ép kiểu ở đúng một chỗ."""
    return cast(dict[str, Any], get_kwargs(cast(Any, WorkerSettings)))

# Job phải tự chạy. `ping` không có ở đây: nó là job nghiệm thu, gọi tay.
PHAI_CO_LICH = {
    # Phase 1 — catalog
    "sync_steam_app_list",
    "sync_steam_details",
    "sync_app_store",
    "sync_google_play",
    # Phase 2 — giá
    "sync_steam_prices",
    "recompute_price_tiers",
    # Phase 3 — thông báo
    "send_notification_digest",
    # Phase 6 — tin tức
    "crawl_all_sources",
    "sync_game_embeddings",
    # Phase 7 — chỉ số và streamer
    "job_fetch_steam_ccu",
    "job_rollup_metrics",
    "job_compute_hotness",
    "job_sync_streamers",
    "job_renew_youtube_websub",
}


def scheduled_names() -> set[str]:
    kwargs = worker_kwargs()
    # arq đặt tên cron là "cron:<tên hàm>".
    return {job.name.removeprefix("cron:") for job in kwargs["cron_jobs"]}


def registered_names() -> set[str]:
    kwargs = worker_kwargs()
    return {func.__name__ for func in kwargs["functions"]}


def test_arq_doc_duoc_worker_settings() -> None:
    """`get_kwargs` đọc thẳng `__dict__` của lớp; sai kiểu khai là hỏng ở đây."""
    kwargs = worker_kwargs()
    assert kwargs["functions"]
    assert kwargs["cron_jobs"]


def test_moi_job_can_dinh_ky_deu_co_trong_lich() -> None:
    thieu = PHAI_CO_LICH - scheduled_names()
    assert not thieu, f"job không có lịch chạy: {sorted(thieu)}"


def test_moi_job_trong_lich_deu_da_dang_ky() -> None:
    """Cron trỏ tới một hàm chưa đăng ký thì worker chết lúc tới giờ, không sớm hơn."""
    la = scheduled_names() - registered_names()
    assert not la, f"job có lịch nhưng chưa đăng ký: {sorted(la)}"


def test_khong_dat_lich_trung_cho_cung_mot_job() -> None:
    names = [job.name for job in worker_kwargs()["cron_jobs"]]
    assert len(names) == len(set(names))
