"""Rollup time-series và chỉ số hot — `docs/PHASE-7.md` mục 4, 5.

Cần Mongo thật: `$dateTrunc`, `$merge` và time-series collection đều là hành vi
của chính MongoDB. Mock lại thì test chỉ kiểm được cái mock — mà cả ba thứ đó
đúng là chỗ bản mock cũ đã bỏ qua.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.services.metrics import (
    HOTNESS,
    compute_hotness,
    hotness_of,
    percentiles,
    top_games,
    update_game_metric,
)
from app.services.rollup import (
    DAILY,
    HOURLY,
    RAW,
    ensure_metrics_collection,
    rollup_time_series,
)

Db = AsyncIOMotorDatabase[dict[str, Any]]

NOW = dt.datetime(2026, 9, 9, 12, 0, tzinfo=dt.UTC)


async def record(db: Db, game_id: str, channel: str, value: int, *, ts: dt.datetime) -> None:
    await update_game_metric(db, game_id, channel, value, ts=ts)


# --- percentile, không cần Mongo -------------------------------------------


def test_percentile_gia_tri_bang_nhau_nhan_cung_diem() -> None:
    """Nếu không thì thứ tự đọc từ database quyết định game nào hot hơn, mà
    thứ tự đó thì tuỳ lúc."""
    out = percentiles({"a": 10.0, "b": 10.0, "c": 99.0})

    assert out["a"] == out["b"]
    assert out["c"] > out["a"]


def test_percentile_lon_nhat_bang_1_va_khong_am() -> None:
    out = percentiles({"a": 1.0, "b": 2.0, "c": 3.0, "d": 4.0})

    assert out["d"] == 1.0
    assert all(0.0 < v <= 1.0 for v in out.values())


def test_percentile_quan_the_rong() -> None:
    assert percentiles({}) == {}


# --- rollup ----------------------------------------------------------------


async def test_tao_dung_time_series_collection(mongo_db: Db) -> None:
    """`SCHEMA.md` bắt `game_metrics` là time-series. Tạo nhầm collection
    thường thì mọi thứ vẫn chạy, chỉ là mất hết phần nén — và tới lúc phát
    hiện thì đã có vài trăm triệu dòng nằm sai chỗ."""
    assert await ensure_metrics_collection(mongo_db) is True
    assert await ensure_metrics_collection(mongo_db) is False  # chạy lại được

    cursor = await mongo_db.list_collections(filter={"name": RAW})
    info = await cursor.to_list(None)
    assert info[0]["type"] == "timeseries"
    assert info[0]["options"]["timeseries"]["timeField"] == "ts"
    assert info[0]["options"]["timeseries"]["metaField"] == "meta"


async def test_gop_raw_thanh_gio_va_ngay(mongo_db: Db) -> None:
    await ensure_metrics_collection(mongo_db)
    base = NOW - dt.timedelta(days=1)
    # Bốn điểm trong cùng một giờ.
    for minute, value in ((0, 100), (15, 300), (30, 200), (45, 400)):
        await record(mongo_db, "g1", "steam_ccu", value, ts=base + dt.timedelta(minutes=minute))

    await rollup_time_series(mongo_db, now=NOW)

    hourly = await mongo_db[HOURLY].find_one({"_id.game_id": "g1"})
    assert hourly is not None
    assert hourly["min"] == 100
    assert hourly["max"] == 400
    assert hourly["avg"] == 250
    assert hourly["samples"] == 4
    assert hourly["peak"] == 400

    daily = await mongo_db[DAILY].find_one({"_id.game_id": "g1"})
    assert daily is not None
    assert daily["peak"] == 400


async def test_gop_lai_khong_nhan_doi(mongo_db: Db) -> None:
    """`$merge` khớp trên `_id` là bộ ba (game, kênh, mốc giờ), nên chạy lại
    chỉ ghi đè đúng bucket đó."""
    await ensure_metrics_collection(mongo_db)
    await record(mongo_db, "g1", "steam_ccu", 100, ts=NOW - dt.timedelta(hours=2))

    await rollup_time_series(mongo_db, now=NOW)
    await rollup_time_series(mongo_db, now=NOW)

    assert await mongo_db[HOURLY].count_documents({}) == 1
    assert await mongo_db[DAILY].count_documents({}) == 1


async def test_tach_bucket_theo_gio_va_theo_kenh(mongo_db: Db) -> None:
    await ensure_metrics_collection(mongo_db)
    await record(mongo_db, "g1", "steam_ccu", 100, ts=NOW - dt.timedelta(hours=2))
    await record(mongo_db, "g1", "steam_ccu", 100, ts=NOW - dt.timedelta(hours=3))
    await record(mongo_db, "g1", "twitch_viewers", 50, ts=NOW - dt.timedelta(hours=2))

    await rollup_time_series(mongo_db, now=NOW)

    assert await mongo_db[HOURLY].count_documents({}) == 3


async def test_xoa_raw_qua_7_ngay_nhung_giu_ban_da_gop(mongo_db: Db) -> None:
    """Thứ tự bắt buộc: gộp trước, xoá sau. Xoá trước là mất dữ liệu chưa kịp
    gộp và không có đường lấy lại."""
    await ensure_metrics_collection(mongo_db)
    await record(mongo_db, "g1", "steam_ccu", 100, ts=NOW - dt.timedelta(days=10))
    await record(mongo_db, "g1", "steam_ccu", 200, ts=NOW - dt.timedelta(hours=1))

    result = await rollup_time_series(mongo_db, now=NOW)

    assert result["raw_deleted"] == 1
    assert await mongo_db[RAW].count_documents({}) == 1
    # Điểm cũ đã kịp vào bản gộp trước khi bị xoá.
    assert await mongo_db[DAILY].count_documents({}) == 2


# --- chỉ số hot ------------------------------------------------------------


async def seed_hotness(db: Db) -> None:
    """Ba game, CCU chênh nhau rõ rệt, trải trên 30 ngày."""
    await ensure_metrics_collection(db)
    plan = {"nho": 100, "vua": 5_000, "lon": 500_000}
    for day in range(1, 30):
        ts = NOW - dt.timedelta(days=day)
        for game_id, ccu in plan.items():
            await record(db, game_id, "steam_ccu", ccu, ts=ts)
    await rollup_time_series(db, now=NOW)


async def test_xep_hang_theo_percentile_khong_theo_so_tuyet_doi(mongo_db: Db) -> None:
    await seed_hotness(mongo_db)

    written = await compute_hotness(mongo_db, now=NOW)

    assert written == 3
    ranked = await top_games(mongo_db, by="score_absolute")
    assert [d["game_id"] for d in ranked] == ["lon", "vua", "nho"]
    # Percentile nằm trong (0, 1], không phải số CCU thô.
    assert all(0.0 < d["score_absolute"] <= 1.0 for d in ranked)


async def test_kenh_don_vi_khac_nhau_khong_nuot_lan_nhau(mongo_db: Db) -> None:
    """CCU đơn vị trăm nghìn, số bài viết đơn vị chục. Cộng thẳng thì CCU nuốt
    sạch và bảng xếp hạng chỉ còn là bảng CCU."""
    await ensure_metrics_collection(mongo_db)
    for day in range(1, 10):
        ts = NOW - dt.timedelta(days=day)
        # "ccu_cao" đông người chơi nhưng không ai viết bài.
        await record(mongo_db, "ccu_cao", "steam_ccu", 900_000, ts=ts)
        await record(mongo_db, "ccu_cao", "vn_articles", 1, ts=ts)
        # "duoc_ban_tan" ngược lại.
        await record(mongo_db, "duoc_ban_tan", "steam_ccu", 1_000, ts=ts)
        await record(mongo_db, "duoc_ban_tan", "vn_articles", 40, ts=ts)
    await rollup_time_series(mongo_db, now=NOW)

    await compute_hotness(mongo_db, now=NOW)

    banter = await hotness_of(mongo_db, "duoc_ban_tan")
    assert banter is not None
    # Thua ở CCU nhưng thắng tuyệt đối ở mảng bài viết -> vẫn có điểm đáng kể,
    # chứ không bị làm tròn về 0 như khi cộng số tuyệt đối.
    assert banter["score_absolute"] > 0.3
    assert banter["scores"]["vn_articles"] == 1.0


async def test_bang_dang_tang_manh_khong_bi_game_top_thuong_truc_chiem_cho(
    mongo_db: Db,
) -> None:
    """Đúng checkpoint của PHASE-7: game luôn ở đỉnh thì momentum ~0, còn game
    vừa bật lên mới là thứ bảng này cần nêu."""
    await ensure_metrics_collection(mongo_db)
    for day in range(1, 30):
        ts = NOW - dt.timedelta(days=day)
        # Luôn đứng đầu, không đổi.
        await record(mongo_db, "thuong_truc", "steam_ccu", 900_000, ts=ts)
        # Bật lên trong tuần gần nhất.
        await record(
            mongo_db, "vua_bat_len", "steam_ccu", 800_000 if day <= 7 else 10, ts=ts
        )
    await rollup_time_series(mongo_db, now=NOW)

    await compute_hotness(mongo_db, now=NOW)

    momentum = await top_games(mongo_db, by="score_momentum")
    assert momentum[0]["game_id"] == "vua_bat_len"
    thuong_truc = await hotness_of(mongo_db, "thuong_truc")
    assert thuong_truc is not None
    assert thuong_truc["score_momentum"] == 0.0


async def test_khong_co_du_lieu_thi_khong_ghi_gi(mongo_db: Db) -> None:
    await ensure_metrics_collection(mongo_db)

    assert await compute_hotness(mongo_db, now=NOW) == 0
    assert await mongo_db[HOTNESS].count_documents({}) == 0


async def test_tinh_lai_khong_nhan_doi_dong(mongo_db: Db) -> None:
    await seed_hotness(mongo_db)

    await compute_hotness(mongo_db, now=NOW)
    await compute_hotness(mongo_db, now=NOW)

    assert await mongo_db[HOTNESS].count_documents({}) == 3


async def test_khong_xep_hang_theo_truong_bat_ky(mongo_db: Db) -> None:
    with pytest.raises(ValueError):
        await top_games(mongo_db, by="ccu_now")
