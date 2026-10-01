"""GalleryService ``sort_by=downloaded_at``（「最近下载」排序）测试。

背景（设计文档 §3.4）：yande_data 表**没有** downloaded_at 列，若沿用
``YandeDataRepository.query()`` 里的 ``getattr(YandeData, sort_by, YandeData.id)``
会静默退化成按 id 排序。因此 GalleryService 必须改用
**download_task 子查询 + JOIN**：

    SELECT yande_data.* FROM yande_data
    JOIN (SELECT image_id, MAX(completed_at) AS t FROM download_tasks
          WHERE status='completed' AND completed_at IS NOT NULL
          GROUP BY image_id) latest ON latest.image_id = yande_data.id
    ORDER BY latest.t DESC

覆盖要点：
1. 排序键是 MAX(completed_at) DESC / ASC（不是 id、不是 created_at）
2. count 语句同样 JOIN 后再 count，否则 total 不对
3. 只出现 status=completed 且 completed_at 非空的图片
4. 其余 filter_funcs（tags / rating / 分辨率）被继承
5. 与既有 random / include_favorite 分支共存且互不干扰（回归）
6. 非 downloaded_at 排序的行为**完全不变**（回归）
"""
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.common.constant import Rating, TaskStatus
from src.dao.database import Base
from src.dao.yande_data_dao import SortBy
from src.middleware.session import _request_session
from src.models.database.my_favorite import MyFavorite
from src.models.database.yande import DownloadTask, YandeData
from src.models.request.gallery import GalleryLoadRequest
from src.services.gallery import GalleryService


@pytest.fixture
def in_memory_session(monkeypatch):
    """干净的 in-memory sqlite + ContextVar session。"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, expire_on_commit=False)
    session = TestSession()
    token = _request_session.set(session)
    monkeypatch.setattr("src.dao.database._get_session_factory", lambda: TestSession)
    try:
        yield session
    finally:
        _request_session.reset(token)
        session.close()


def _seed_yande(sess, image_id: int, tags: str = "a", down: bool = True,
                width: int = 100, rating=Rating.S) -> None:
    sess.add(
        YandeData(
            id=image_id,
            tags=tags,
            width=width,
            height=100,
            file_ext="jpg",
            file_size=1024,
            file_url=f"http://a/{image_id}.jpg",
            preview_url=f"http://pa/{image_id}.jpg",
            md5=f"m{image_id}",
            author="t",
            # created_at 故意与下载完成时间**相反**的顺序：
            # 若实现误用 created_at / id 排序，断言会立刻失败
            created_at=datetime(2024, 1, 1) + timedelta(days=image_id),
            down_flag=down,
            rating=rating,
        )
    )


def _seed_task(sess, task_id, image_id, status, completed_at) -> None:
    sess.add(
        DownloadTask(
            task_id=task_id,
            image_id=image_id,
            file_name=f"{image_id}.jpg",
            status=status,
            created_at=datetime(2024, 1, 1),
            updated_at=datetime(2024, 1, 1),
            completed_at=completed_at,
        )
    )


@pytest.fixture
def seeded(in_memory_session):
    """固定数据集（完成时间顺序与 id / created_at 顺序刻意相反）。

    | image | down | completed_at | 期望 |
    |-------|------|--------------|------|
    | 1 | T | now-1d  | 排第 1 |
    | 2 | T | now-5d  | 排第 2 |
    | 3 | T | now-3d + now-9d（重复下载） | 排第 3，取 MAX=now-3d |
    | 4 | T | NULL（跳过下载） | 不出现 |
    | 5 | T | 无任务 | 不出现 |
    | 6 | F | now-2d | 不出现（未下载，过滤器 down_flag=True） |
    | 7 | T | failed @ now | 不出现（非 completed） |
    """
    now = datetime.now()
    for i in range(1, 8):
        # image 6 是唯一 down_flag=False 的图片（用于验证既有过滤器仍生效）
        _seed_yande(in_memory_session, i, tags="common", down=(i != 6))
    in_memory_session.commit()

    _seed_task(in_memory_session, "t1", 1, TaskStatus.COMPLETED, now - timedelta(days=1))
    _seed_task(in_memory_session, "t2", 2, TaskStatus.COMPLETED, now - timedelta(days=5))
    _seed_task(in_memory_session, "t3a", 3, TaskStatus.COMPLETED, now - timedelta(days=9))
    _seed_task(in_memory_session, "t3b", 3, TaskStatus.COMPLETED, now - timedelta(days=3))
    _seed_task(in_memory_session, "t4", 4, TaskStatus.COMPLETED, None)
    _seed_task(in_memory_session, "t6", 6, TaskStatus.COMPLETED, now - timedelta(days=2))
    _seed_task(in_memory_session, "t7", 7, TaskStatus.FAILED, now - timedelta(days=2))
    in_memory_session.commit()
    return in_memory_session


def _load(**overrides):
    """调用 query_local_database，config 开关全部关闭（走纯 downloaded_at 分支）。

    参数直接透传给 GalleryLoadRequest。
    """
    params = GalleryLoadRequest(**{"page": 1, "page_size": 20, **overrides})
    with patch("src.services.gallery.config") as mock_config:
        mock_config.favorites.enable_my_favorites = False
        return GalleryService.query_local_database(params)


# ============================================================
# 枚举 + 排序分支入口
# ============================================================


def test_sort_by_enum_exposes_downloaded_at():
    """SortBy 枚举新增 DOWNLOADED_AT（前端 sort_by=downloaded_at 的契约入口）。"""
    assert SortBy.DOWNLOADED_AT.value == "downloaded_at"
    # str 枚举：与裸字符串比较为 True（前端直接传字符串）
    assert SortBy.DOWNLOADED_AT == "downloaded_at"


def test_yande_data_has_no_downloaded_at_column():
    """锁定前提：yande_data 表**没有** downloaded_at 列，所以必须走 JOIN 子查询。"""
    assert not hasattr(YandeData, "downloaded_at"), (
        "若将来真的加了 downloaded_at 列，需重新评估 _query_local_with_options 的 JOIN 分支"
    )


def test_downloaded_at_sort_is_not_plain_id_order(seeded):
    """若误走 YandeDataRepository.query()（getattr 退化为按 id 排序），此断言会失败。"""
    images, _ = _load(sort_by="downloaded_at", sort_order="desc")
    ids = [i.id for i in images]
    assert ids != sorted(ids, reverse=True)


# ============================================================
# 排序正确性
# ============================================================


def test_sort_downloaded_at_desc(seeded):
    """DESC：按最新完成时间倒序。"""
    images, total = _load(sort_by="downloaded_at", sort_order="desc")
    assert [i.id for i in images] == [1, 3, 2], (
        f"期望 [1, 3, 2]，实际 {[i.id for i in images]}"
    )
    assert total == 3, f"total 必须 JOIN 后再 count，期望 3，实际 {total}"


def test_sort_downloaded_at_asc(seeded):
    """ASC：按最早完成时间正序（与 DESC 严格反序）。"""
    images, _ = _load(sort_by="downloaded_at", sort_order="asc")
    assert [i.id for i in images] == [2, 3, 1]


def test_sort_downloaded_at_uses_max_not_min(seeded):
    """重复下载取 MAX：image 3 按 now-3d（而不是更早的 now-9d）参与排序。"""
    images, _ = _load(sort_by="downloaded_at", sort_order="desc")
    ids = [i.id for i in images]
    # 3 排在 2（now-5d）之前，证明用的是 MAX(now-3d) 而非 MIN(now-9d)
    assert ids.index(3) < ids.index(2)


def test_sort_downloaded_at_excludes_null_completed_at(seeded):
    """completed_at 为 NULL 的图片不出现（否则排序键为 NULL，行为不可预期）。"""
    images, _ = _load(sort_by="downloaded_at")
    assert 4 not in [i.id for i in images]


def test_sort_downloaded_at_excludes_non_completed(seeded):
    """failed 任务对应的图片不出现。"""
    images, _ = _load(sort_by="downloaded_at")
    assert 7 not in [i.id for i in images]


def test_sort_downloaded_at_excludes_not_downloaded_images(seeded):
    """down_flag=False 的图片被既有过滤器排除（image 6）。"""
    images, total = _load(sort_by="downloaded_at")
    assert 6 not in [i.id for i in images]
    assert total == 3


def test_sort_downloaded_at_dedupes_repeated_downloads(seeded):
    """同一张图多条 completed 任务只出现一次。"""
    images, total = _load(sort_by="downloaded_at")
    ids = [i.id for i in images]
    assert len(ids) == len(set(ids)), f"出现重复 id：{ids}"
    assert total == len(ids)


# ============================================================
# 分页
# ============================================================


def test_sort_downloaded_at_respects_pagination(seeded):
    """分页在 JOIN 之后切分，且 total 是全量（不是当页条数）。"""
    page1, total1 = _load(sort_by="downloaded_at", sort_order="desc", page=1, page_size=2)
    page2, total2 = _load(sort_by="downloaded_at", sort_order="desc", page=2, page_size=2)
    assert [i.id for i in page1] == [1, 3]
    assert [i.id for i in page2] == [2]
    assert total1 == total2 == 3


# ============================================================
# 继承其余 filter_funcs
# ============================================================


def test_downloaded_at_sort_inherits_tag_filter(seeded):
    """tags 过滤仍生效（命中则保留，未命中则过滤掉）。"""
    _seed_yande(seeded, 8, tags="common marked")
    _seed_task(
        seeded, "t8", 8, TaskStatus.COMPLETED, datetime.now() - timedelta(days=0.5)
    )
    seeded.commit()
    images, total = _load(sort_by="downloaded_at", sort_order="desc", tags="marked")
    assert [i.id for i in images] == [8]
    assert total == 1


def test_downloaded_at_sort_inherits_rating_filter(seeded):
    """rating 过滤仍生效。"""
    images, _ = _load(sort_by="downloaded_at", rating=[Rating.R18])
    assert images == []


def test_downloaded_at_sort_inherits_resolution_filter(seeded):
    """分辨率（min_width）过滤仍生效。"""
    _seed_yande(seeded, 9, tags="common", width=4000)
    _seed_task(
        seeded, "t9", 9, TaskStatus.COMPLETED, datetime.now() - timedelta(days=0.5)
    )
    seeded.commit()
    images, _ = _load(sort_by="downloaded_at", sort_order="desc", min_width=2000)
    assert [i.id for i in images] == [9]


# ============================================================
# 与既有分支共存（回归）
# ============================================================


def test_downloaded_at_sort_with_random_branch(seeded):
    """random=True 与 downloaded_at 共存：走 random 排序，但结果仍限定在有 completed 任务的图片内。"""
    images, total = _load(sort_by="downloaded_at", random=True)
    ids = [i.id for i in images]
    assert set(ids) == {1, 2, 3}
    assert total == 3


def test_downloaded_at_sort_with_include_favorite_branch(seeded):
    """include_favorite_status=True 与 downloaded_at 共存，两个 JOIN 同时生效。"""
    seeded.add(MyFavorite(image_id=2, created_at=datetime(2026, 1, 1)))
    seeded.commit()
    params = GalleryLoadRequest(
        page=1, page_size=20, sort_by="downloaded_at", sort_order="desc",
        include_favorite_status=True,
    )
    with patch("src.services.gallery.config") as mock_config:
        mock_config.favorites.enable_my_favorites = True
        images, total = GalleryService.query_local_database(params)
    flags = {i.id: i.is_favorited for i in images}
    assert list(flags) == [1, 3, 2]
    assert flags == {1: False, 3: False, 2: True}
    assert total == 3


def test_non_downloaded_at_sort_unchanged(seeded):
    """回归：sort_by=id/created_at 的老行为完全不变（仍走 YandeDataRepository.query）。"""
    images, total = _load(sort_by="id", sort_order="desc")
    # 仍只按 down_flag=True 过滤（image 6 被排除），download_task 状态完全不参与
    assert [i.id for i in images] == [7, 5, 4, 3, 2, 1]
    assert total == 6


def test_random_branch_without_downloaded_at_unchanged(seeded):
    """回归：random=True 且非 downloaded_at 时行为不变（去重 + 全部已下载图片）。"""
    images, _ = _load(random=True)
    ids = [i.id for i in images]
    assert set(ids) == {1, 2, 3, 4, 5, 7}  # image 6 down_flag=False 被排除
    assert len(ids) == len(set(ids))
