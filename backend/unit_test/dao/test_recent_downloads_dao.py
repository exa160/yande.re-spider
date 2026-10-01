"""DownloadTaskDao「最近下载」4 个方法的单元测试。

覆盖设计文档 §5「后端」表格中 DAO 相关的全部用例，并锁定 §2.4 的**安全红线**：
``delete_completed_before`` / ``delete_all_completed`` **绝不**删除
pending / downloading / paused / failed / cancelled 记录。

三个筛选条件（缺一不可）各自的测试断言：
1. ``status == COMPLETED``        → 非 completed 记录一律不出现（列表/计数/删除）
2. ``completed_at IS NOT NULL``  → 「文件已存在跳过下载」分支产生的 NULL 被排除
3. ``GROUP BY image_id`` + MAX   → 重复下载去重，排序键取最新完成时间

DB 约定：in-memory SQLite + 显式传入 session（``DownloadTaskDao(session)``），
与 test_my_favorite_dao.py 同款，避免触达真实 sqlite 文件。
"""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.common.constant import TaskStatus
from src.dao.database import Base
from src.dao.download_task_dao import DownloadTaskDao
from src.models.database.yande import DownloadTask


@pytest.fixture
def session():
    """in-memory SQLite session（显式建表）。"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()


@pytest.fixture
def dao(session):
    """绑定到测试 session 的 DAO 实例（owns_session=False，不会 commit/close）。"""
    return DownloadTaskDao(session)


def _add(session, task_id, image_id, status, completed_at):
    session.add(
        DownloadTask(
            task_id=task_id,
            image_id=image_id,
            file_name=f"{image_id}.jpg",
            status=status,
            created_at=datetime(2026, 1, 1),
            updated_at=datetime(2026, 1, 1),
            completed_at=completed_at,
        )
    )
    session.flush()


NOW = datetime(2026, 6, 1, 12, 0, 0)


@pytest.fixture
def seeded(session):
    """覆盖全部状态/时间组合的固定数据集。

    | image | 记录 | 期望 |
    |-------|------|------|
    | 1 | completed @ now-1d           | 命中（最新） |
    | 2 | completed @ now-10d          | 命中（最旧） |
    | 3 | completed @ now-5d + now-2d  | 命中 1 条，MAX=now-2d（去重） |
    | 4 | completed @ NULL             | 排除（跳过下载分支） |
    | 5 | failed @ now-3d              | 排除（非 completed） |
    | 6 | pending / downloading / paused / cancelled | 全部排除 |
    | 7 | completed @ now-40d         | 命中（用于 days 清除测试） |
    """
    _add(session, "t1", 1, TaskStatus.COMPLETED, NOW - timedelta(days=1))
    _add(session, "t2", 2, TaskStatus.COMPLETED, NOW - timedelta(days=10))
    _add(session, "t3a", 3, TaskStatus.COMPLETED, NOW - timedelta(days=5))
    _add(session, "t3b", 3, TaskStatus.COMPLETED, NOW - timedelta(days=2))
    _add(session, "t4", 4, TaskStatus.COMPLETED, None)
    _add(session, "t5", 5, TaskStatus.FAILED, NOW - timedelta(days=3))
    _add(session, "t6a", 6, TaskStatus.PENDING, None)
    _add(session, "t6b", 6, TaskStatus.DOWNLOADING, None)
    _add(session, "t6c", 6, TaskStatus.PAUSED, None)
    _add(session, "t6d", 6, TaskStatus.CANCELLED, None)
    _add(session, "t7", 7, TaskStatus.COMPLETED, NOW - timedelta(days=40))
    session.commit()
    return session


# ============================================================
# list_completed_image_ids
# ============================================================


def test_list_orders_by_max_completed_at_desc(dao, seeded):
    """按 MAX(completed_at) DESC 排序（不是 created_at，也不是 image_id）。"""
    rows = dao.list_completed_image_ids(page=1, page_size=20)
    assert [r[0] for r in rows] == [1, 3, 2, 7], (
        f"期望按完成时间倒序 [1, 3, 2, 7]，实际 {[r[0] for r in rows]}"
    )


def test_list_dedupes_multiple_tasks_for_same_image(dao, seeded):
    """同一 image_id 的多条 completed 记录只返回 1 条，且取 MAX(completed_at)。"""
    rows = dao.list_completed_image_ids(page=1, page_size=20)
    ids = [r[0] for r in rows]
    assert ids.count(3) == 1, f"image 3 重复出现：{ids}"
    latest = dict((r[0], r[1]) for r in rows)[3]
    assert latest == NOW - timedelta(days=2), f"应取 MAX(completed_at)，实际 {latest}"


def test_list_excludes_null_completed_at(dao, seeded):
    """completed_at 为 NULL 的 completed 记录（跳过下载分支）必须被排除。"""
    ids = [r[0] for r in dao.list_completed_image_ids(page=1, page_size=20)]
    assert 4 not in ids, f"image 4 的 completed_at 为 NULL，不应出现：{ids}"


def test_list_excludes_non_completed_statuses(dao, seeded):
    """failed / pending / downloading / paused / cancelled 一律不出现。"""
    ids = [r[0] for r in dao.list_completed_image_ids(page=1, page_size=20)]
    for excluded in (5, 6):
        assert excluded not in ids, f"image {excluded} 非 completed，不应出现：{ids}"


def test_list_respects_pagination(dao, seeded):
    """分页按 MAX(completed_at) DESC 切分，两页拼接后与全量一致。"""
    page1 = dao.list_completed_image_ids(page=1, page_size=2)
    page2 = dao.list_completed_image_ids(page=2, page_size=2)
    assert [r[0] for r in page1] == [1, 3]
    assert [r[0] for r in page2] == [2, 7]
    assert len(page1) + len(page2) == dao.count_completed_distinct_images()


def test_list_returns_empty_when_no_records(dao, session):
    """空表返回空列表。"""
    assert dao.list_completed_image_ids(page=1, page_size=10) == []


# ============================================================
# count_completed_distinct_images
# ============================================================


def test_count_is_distinct_by_image(dao, seeded):
    """COUNT(DISTINCT image_id)：image 3 的两条 completed 只算 1。"""
    assert dao.count_completed_distinct_images() == 4


def test_count_excludes_null_and_non_completed(dao, seeded):
    """计数与列表口径完全一致（排除 NULL completed_at 与非 completed）。"""
    listed = {r[0] for r in dao.list_completed_image_ids(page=1, page_size=100)}
    assert dao.count_completed_distinct_images() == len(listed)


def test_count_returns_zero_when_empty(dao, session):
    """空表返回 0。"""
    assert dao.count_completed_distinct_images() == 0


# ============================================================
# delete_all_completed —— 安全红线
# ============================================================


def test_delete_all_completed_never_deletes_non_completed(dao, seeded):
    """安全红线：全清**绝不**删除 pending/downloading/paused/failed/cancelled。

    失败模式：任一非 completed 的 task_id 从库里消失即回归。
    """
    deleted = dao.delete_all_completed()
    # 注意口径：rowcount 统计的是**任务记录条数**（t3a/t3b 是 image 3 的两条重复任务），
    # 不是去重图片数；去重图片数是 4。
    assert deleted == 5, f"应删 5 条 completed 任务记录，实际 {deleted}"

    remaining = {r.task_id: r for r in seeded.query(DownloadTask).all()}
    for task_id in ("t6a", "t6b", "t6c", "t6d"):
        assert task_id in remaining, f"非 completed 记录 {task_id} 被误删！"
        assert remaining[task_id].status == (
            TaskStatus.PENDING
            if task_id == "t6a"
            else TaskStatus.DOWNLOADING
            if task_id == "t6b"
            else TaskStatus.PAUSED
            if task_id == "t6c"
            else TaskStatus.CANCELLED
        )
    assert "t5" in remaining, "failed 记录被误删！"
    assert remaining["t5"].status == TaskStatus.FAILED


def test_delete_all_completed_keeps_completed_with_null(dao, seeded):
    """completed_at 为 NULL 的 completed 记录**保留**（与列表口径对齐，设计 §3.1）。"""
    dao.delete_all_completed()
    remaining = {r.task_id for r in seeded.query(DownloadTask).all()}
    assert "t4" in remaining, "completed_at 为 NULL 的记录不在删除范围内"
    assert dao.count_completed_distinct_images() == 0


def test_delete_all_completed_returns_zero_when_nothing(dao, session):
    """无匹配时返回 0（幂等）。"""
    assert dao.delete_all_completed() == 0


# ============================================================
# delete_completed_before —— 安全红线
# ============================================================


def test_delete_completed_before_only_deletes_older(dao, seeded):
    """只删 completed_at < cutoff 的记录。"""
    deleted = dao.delete_completed_before(NOW - timedelta(days=30))
    assert deleted == 1, f"应只删 image 7（now-40d），实际 {deleted}"
    ids = [r[0] for r in dao.list_completed_image_ids(page=1, page_size=20)]
    assert 7 not in ids and set(ids) == {1, 3, 2}


def test_delete_completed_before_never_deletes_non_completed(dao, seeded):
    """安全红线：按时间清除同样**绝不**删除非 completed 记录。

    即使给一个「未来时间」作为 cutoff（逻辑上会匹配一切），非 completed 仍必须存活。
    """
    dao.delete_completed_before(NOW + timedelta(days=365))
    remaining = {r.task_id for r in seeded.query(DownloadTask).all()}
    for task_id in ("t5", "t6a", "t6b", "t6c", "t6d"):
        assert task_id in remaining, f"非 completed 记录 {task_id} 被误删！"
    # completed 里只有 completed_at 为 NULL 的 t4 因 IS NOT NULL 条件而幸存
    assert remaining == {"t4", "t5", "t6a", "t6b", "t6c", "t6d"}


def test_delete_completed_before_returns_zero_when_none_match(dao, seeded):
    """cutoff 早于全部记录时返回 0。"""
    assert dao.delete_completed_before(NOW - timedelta(days=365)) == 0
    assert dao.count_completed_distinct_images() == 4
