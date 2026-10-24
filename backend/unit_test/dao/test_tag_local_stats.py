"""TagRepository.calculate_local_stats 批量 upsert 正确性 / 幂等性。

背景（2026-10-25 优化）：
- 旧实现逐个 ORM 对象更新/插入 TagLocalStats，全量重算时 mutate + flush
  是最大开销；现改为 chunked INSERT ... ON CONFLICT DO UPDATE。
- 统计口径不变：只统计 down_flag=True 的图片，且只落库已存在于 YandeTag 的标签。
"""
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.dao.tag_dao import TagRepository
from src.models.database.yande import Base, TagLocalStats, YandeData, YandeTag


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


def _seed(TestSession, images, tags) -> None:
    """images: [(tags_str, down_flag), ...]；tags: [(id, name), ...]"""
    s = TestSession()
    for tag_id, name in tags:
        s.add(YandeTag(id=tag_id, name=name, count=0, type=0, ambiguous=False))
    for i, (tags_str, down_flag) in enumerate(images, start=1):
        s.add(
            YandeData(
                id=i,
                tags=tags_str,
                width=100,
                height=100,
                file_ext="jpg",
                file_size=1024,
                file_url=f"http://a/{i}.jpg",
                preview_url=f"http://pa/{i}.jpg",
                md5=f"m{i}",
                author="t",
                created_at=datetime(2024, 1, 1),
                down_flag=down_flag,
            )
        )
    s.commit()
    s.close()


def _read_stats(TestSession) -> dict[int, int]:
    s = TestSession()
    try:
        return {row.tag_id: row.local_count for row in s.query(TagLocalStats).all()}
    finally:
        s.close()


def test_calculate_local_stats_counts_only_downloaded_and_cached(in_memory_db):
    _seed(
        in_memory_db,
        images=[
            ("a b", True),
            ("a c", True),
            ("a d", False),  # 未下载 → 不参与统计
            ("a e", True),   # e 不在 YandeTag 缓存 → 跳过
        ],
        tags=[(1, "a"), (2, "b"), (3, "c")],
    )

    with TagRepository() as repo:
        updated = repo.calculate_local_stats()

    assert updated == 3
    # a 出现在 3 张已下载图（a b / a c / a e）；d 只在未下载图里，e 不在缓存
    assert _read_stats(in_memory_db) == {1: 3, 2: 1, 3: 1}


def test_calculate_local_stats_idempotent_on_second_run(in_memory_db):
    _seed(
        in_memory_db,
        images=[("a b", True), ("a c", True)],
        tags=[(1, "a"), (2, "b"), (3, "c")],
    )

    with TagRepository() as repo:
        repo.calculate_local_stats()
    first = _read_stats(in_memory_db)

    with TagRepository() as repo:
        repo.calculate_local_stats()

    # 再跑一次只做 upsert，不产生重复行/翻倍计数
    assert _read_stats(in_memory_db) == first == {1: 2, 2: 1, 3: 1}

    s = in_memory_db()
    try:
        assert s.query(TagLocalStats).count() == 3
    finally:
        s.close()


def test_calculate_local_stats_sets_last_calculated(in_memory_db):
    _seed(
        in_memory_db,
        images=[("a", True)],
        tags=[(1, "a")],
    )

    with TagRepository() as repo:
        repo.calculate_local_stats()

    with TagRepository() as repo:
        last = repo.get_local_stats_last_calculated()

    assert last is not None
    assert (datetime.now() - last).total_seconds() < 60


def test_calculate_local_stats_empty_downloads_returns_zero(in_memory_db):
    _seed(
        in_memory_db,
        images=[("a", False)],
        tags=[(1, "a")],
    )

    with TagRepository() as repo:
        assert repo.calculate_local_stats() == 0
    assert _read_stats(in_memory_db) == {}
