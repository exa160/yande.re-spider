"""TagCacheService.calculate_local_stats 的两道门禁 + 返回结构。

门禁：
1. 下载队列连续空闲 < 5 分钟 → skipped=download_busy（不做全表扫描）
2. 上次全量计算时间不早于最近一次下载完成 → skipped=up_to_date

返回结构供前端判断是否刷新标签列表 / 安排重试。
"""
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.dao.download_task_dao import DownloadTaskDao
from src.infrastructure.download_queue import download_queue
from src.models.database.yande import Base, TagLocalStats, YandeData, YandeTag
from src.services.tag_cache import TagCacheService


@pytest.fixture
def in_memory_db(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr("src.dao.database._get_session_factory", lambda: TestSession)
    return TestSession


def _seed(TestSession, last_calculated=None, local_count=0) -> None:
    s = TestSession()
    s.add(YandeTag(id=1, name="a", count=0, type=0, ambiguous=False))
    s.add(
        YandeData(
            id=1,
            tags="a",
            width=100,
            height=100,
            file_ext="jpg",
            file_size=1024,
            file_url="http://a/1.jpg",
            preview_url="http://pa/1.jpg",
            md5="m1",
            author="t",
            created_at=datetime(2024, 1, 1),
            down_flag=True,
        )
    )
    if last_calculated is not None:
        s.add(
            TagLocalStats(
                tag_id=1,
                local_count=local_count,
                last_calculated=last_calculated,
            )
        )
    s.commit()
    s.close()


def _patch_idle(monkeypatch, seconds: float) -> None:
    monkeypatch.setattr(download_queue, "get_idle_seconds", lambda: seconds)


def _patch_latest_download(monkeypatch, value) -> None:
    monkeypatch.setattr(
        DownloadTaskDao, "max_completed_at", lambda self: value
    )


def _stats(TestSession) -> dict[int, int]:
    s = TestSession()
    try:
        return {r.tag_id: r.local_count for r in s.query(TagLocalStats).all()}
    finally:
        s.close()


def test_busy_queue_skips_without_scanning(in_memory_db, monkeypatch):
    _seed(in_memory_db)
    _patch_idle(monkeypatch, 10.0)
    _patch_latest_download(monkeypatch, datetime(2025, 1, 1))

    result = TagCacheService.calculate_local_stats()

    assert result["success"] is True
    assert result["calculated"] is False
    assert result["skipped"] == "download_busy"
    assert result["tags_updated"] == 0
    assert result["idle_seconds"] == 10.0
    assert result["min_idle_seconds"] == 300.0
    assert _stats(in_memory_db) == {}


def test_up_to_date_skips_when_last_calc_after_latest_download(
    in_memory_db, monkeypatch
):
    _seed(in_memory_db, last_calculated=datetime(2025, 6, 1), local_count=99)
    _patch_idle(monkeypatch, 400.0)
    _patch_latest_download(monkeypatch, datetime(2025, 1, 1))

    result = TagCacheService.calculate_local_stats()

    assert result["calculated"] is False
    assert result["skipped"] == "up_to_date"
    assert _stats(in_memory_db) == {1: 99}


def test_no_download_history_with_existing_stats_is_up_to_date(
    in_memory_db, monkeypatch
):
    _seed(in_memory_db, last_calculated=datetime(2025, 6, 1), local_count=99)
    _patch_idle(monkeypatch, 400.0)
    _patch_latest_download(monkeypatch, None)

    result = TagCacheService.calculate_local_stats()

    assert result["calculated"] is False
    assert result["skipped"] == "up_to_date"


def test_stale_stats_recalculates(in_memory_db, monkeypatch):
    _seed(in_memory_db, last_calculated=datetime(2025, 1, 1), local_count=99)
    _patch_idle(monkeypatch, 400.0)
    _patch_latest_download(monkeypatch, datetime(2025, 6, 1))

    result = TagCacheService.calculate_local_stats()

    assert result["calculated"] is True
    assert result["skipped"] is None
    assert result["tags_updated"] == 1
    assert _stats(in_memory_db) == {1: 1}


def test_first_run_without_stats_recalculates(in_memory_db, monkeypatch):
    _seed(in_memory_db)
    _patch_idle(monkeypatch, 400.0)
    _patch_latest_download(monkeypatch, datetime(2025, 6, 1))

    result = TagCacheService.calculate_local_stats()

    assert result["calculated"] is True
    assert result["tags_updated"] == 1
    assert _stats(in_memory_db) == {1: 1}
