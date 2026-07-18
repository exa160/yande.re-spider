"""task_store.get_tasks 内存合并测试（TDD）

Bug: commit 38914a3 把 task_store.get_tasks 从"读内存"改成"读 DB"，
导致下载中的进度/速度永远 stale（progress_callback 只更新内存，不写 DB）。

修复：合并策略 — DB 读所有匹配，再用内存中的活跃任务（pending/downloading/paused）
实时 progress/speed/downloaded_size 覆盖 DB 返回值。

仅活跃状态需要合并（paused 也在内存中但 progress_callback 已停，DB 值与内存一致）。
"""
from datetime import datetime

import pytest

from src.common.constant import TaskStatus
from src.dao.download_task_dao import DownloadTaskDao
from src.models.database.yande import DownloadTask


@pytest.fixture
def dao():
    with DownloadTaskDao() as d:
        d.session.query(DownloadTask).delete()
        yield d


def _insert_task(dao, task_id, image_id, file_name, status, **overrides):
    """通过 ORM 直接插入任务"""
    defaults = dict(
        task_id=task_id,
        image_id=image_id,
        file_name=file_name,
        status=status,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    defaults.update(overrides)
    rec = DownloadTask(**defaults)
    dao.session.add(rec)
    dao.session.flush()
    return rec


# ===== Test: 内存覆盖 =====

def test_get_tasks_overrides_progress_with_in_memory_value(dao):
    """内存中 downloading 任务的 progress 应覆盖 DB 中的 stale 值"""
    _insert_task(dao, "d-1", 100, "d.jpg", TaskStatus.DOWNLOADING,
                 progress=0.1, downloaded_size=1000, speed=500.0)

    # 直接通过 task_store 模拟内存中的实时更新（不通过 update_task，因为那是实现细节）
    from src.infrastructure.download_queue import task_store
    # 清空 task_store 内存（避免 fixture 残留）
    with task_store._lock:
        task_store._tasks.clear()
    task_store._tasks["d-1"] = task_store.DownloadTask(
        task_id="d-1",
        status=TaskStatus.DOWNLOADING,
        progress=0.75,
        downloaded_size=7500,
        speed=2048.0,
        file_name="d.jpg",
        file_size=10000,
        started_at=datetime.now().isoformat(),
        completed_at=None,
        created_at=datetime.now().isoformat(),
    )

    tasks, total = task_store.get_tasks(status=TaskStatus.DOWNLOADING)
    assert total == 1
    assert len(tasks) == 1
    assert tasks[0]["task_id"] == "d-1"
    assert tasks[0]["progress"] == 0.75, f"应从内存读取 0.75，实际 {tasks[0]['progress']}"
    assert tasks[0]["speed"] == 2048.0
    assert tasks[0]["downloaded_size"] == 7500

    # 清理
    with task_store._lock:
        task_store._tasks.clear()


def test_get_tasks_keeps_db_value_when_not_in_memory(dao):
    """内存中没有的 task 应保留 DB 原始值（终态任务不合并）"""
    _insert_task(dao, "c-1", 200, "c.jpg", TaskStatus.COMPLETED,
                 progress=1.0, downloaded_size=5000, speed=0.0)

    from src.infrastructure.download_queue import task_store
    with task_store._lock:
        task_store._tasks.clear()
    # 内存中无 c-1（completed 任务不在内存中）

    tasks, total = task_store.get_tasks(status=TaskStatus.COMPLETED)
    assert total == 1
    assert tasks[0]["task_id"] == "c-1"
    assert tasks[0]["progress"] == 1.0
    assert tasks[0]["downloaded_size"] == 5000


def test_get_tasks_does_not_override_completed_query(dao):
    """查询 completed 时不应合并内存（completed 不在内存，DB 完整）"""
    _insert_task(dao, "c-2", 300, "c2.jpg", TaskStatus.COMPLETED,
                 progress=0.5, downloaded_size=3000, speed=100.0)

    from src.infrastructure.download_queue import task_store
    with task_store._lock:
        task_store._tasks.clear()
        # 即使内存有同名 task（不可能，但模拟 race condition）
        task_store._tasks["c-2"] = task_store.DownloadTask(
            task_id="c-2",
            status=TaskStatus.DOWNLOADING,
            progress=0.99,
            downloaded_size=9900,
            speed=9999.0,
            file_name="c2.jpg",
            file_size=10000,
            started_at=datetime.now().isoformat(),
            completed_at=None,
            created_at=datetime.now().isoformat(),
        )

    tasks, total = task_store.get_tasks(status=TaskStatus.COMPLETED)
    # 查询 completed 状态 → 只从 DB 读 → progress=0.5（DB 值，不被内存覆盖）
    assert tasks[0]["progress"] == 0.5, (
        f"completed 查询不应受内存覆盖影响，实际 {tasks[0]['progress']}"
    )
    assert tasks[0]["speed"] == 100.0

    with task_store._lock:
        task_store._tasks.clear()