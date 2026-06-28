"""TaskStore.recreate_task / get_pending_task_ids 单测（cancelled 重试 + 重启恢复）

依赖：
- TaskStore._tasks 内部状态（操作内存缓存，不依赖 DB 真实数据）
- 隔离：用 task_store 的实例方法 + 直接清空 _tasks 避免污染
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]) + "/backend")

import pytest

from src.common.constant import TaskStatus
from src.dao.download_task_dao import DownloadTaskDao
from src.infrastructure.download_queue import task_store
from src.models.database.yande import YandeData


# ---- fixtures ----

@pytest.fixture
def fresh_store():
    """每个用例前后清空 task_store 内存缓存。"""
    with task_store._lock:
        task_store._tasks.clear()
    yield task_store
    with task_store._lock:
        task_store._tasks.clear()


def _make_yande_data(image_id: int) -> YandeData:
    """构造一个最小可用的 YandeData ORM 实例用于 recreate_task 测试"""
    return YandeData(
        id=image_id,
        file_ext="jpg",
        file_url=f"https://files.yande.re/sample/{image_id}.jpg",
        md5=None,
        file_size=1024 * 100,
    )


# ---- get_pending_task_ids ----

def test_get_pending_task_ids_empty(fresh_store):
    """空 store 返回空列表"""
    assert fresh_store.get_pending_task_ids() == []


def test_get_pending_task_ids_returns_only_pending(fresh_store):
    """只返回 PENDING 状态的 task_id，不返回 PAUSED / COMPLETED / FAILED / CANCELLED"""
    # 直接构造内存 task（不通过 create_task，避免依赖 DB）
    from src.infrastructure.download_queue import TaskStore

    for tid, status in [
        ("p-1", TaskStatus.PENDING),
        ("p-2", TaskStatus.PENDING),
        ("pa-1", TaskStatus.PAUSED),
        ("c-1", TaskStatus.COMPLETED),
        ("f-1", TaskStatus.FAILED),
        ("x-1", TaskStatus.CANCELLED),
        ("d-1", TaskStatus.DOWNLOADING),
    ]:
        fresh_store._tasks[tid] = TaskStore.DownloadTask(
            task_id=tid, file_name=f"{tid}.jpg"
        )
        fresh_store._tasks[tid].status = status

    result = fresh_store.get_pending_task_ids()
    assert sorted(result) == ["p-1", "p-2"]


# ---- recreate_task ----

def test_recreate_task_inserts_into_memory(fresh_store):
    """recreate_task 应该把 task 注入 _tasks"""
    yande_data = _make_yande_data(image_id=12345)
    task = fresh_store.recreate_task("recreate-1", yande_data)

    assert task.task_id == "recreate-1"
    assert task.yande_data is yande_data
    assert task.status == TaskStatus.PENDING  # 默认值
    assert task.progress == 0.0
    assert task.downloaded_size == 0

    # 内存里有这个 task
    assert "recreate-1" in fresh_store._tasks
    assert fresh_store._tasks["recreate-1"] is task


def test_recreate_task_does_not_touch_db(fresh_store):
    """recreate_task 只操作内存，不写 DB（DB 中 task 记录已存在）"""
    yande_data = _make_yande_data(image_id=99999)
    task_id = "recreate-no-db-write"

    # 清理 download_tasks 表
    with DownloadTaskDao() as dao:
        from src.models.database.yande import DownloadTask
        dao.session.query(DownloadTask).filter_by(task_id=task_id).delete()

    fresh_store.recreate_task(task_id, yande_data)

    # DB 中不应该有这个 task（recreate_task 不写 DB）
    with DownloadTaskDao() as dao:
        from src.models.database.yande import DownloadTask
        rec = dao.session.query(DownloadTask).filter_by(task_id=task_id).first()
        assert rec is None

    # 但内存里有
    assert task_id in fresh_store._tasks


def test_recreate_task_overwrites_existing(fresh_store):
    """recreate_task 在内存已有同名 task 时应该覆盖（cancelled 后内存被清理，
    但理论上重入防护：同一 task_id 重复 recreate 应该用新 yande_data 覆盖）"""
    yande_data_old = _make_yande_data(image_id=100)
    yande_data_new = _make_yande_data(image_id=200)

    fresh_store.recreate_task("dup", yande_data_old)
    fresh_store.recreate_task("dup", yande_data_new)

    assert fresh_store._tasks["dup"].yande_data is yande_data_new


def test_recreate_task_uses_yande_data_filename(fresh_store):
    """recreate_task 应该用 yande_data 的 id 和 ext 构造 file_name"""
    yande_data = _make_yande_data(image_id=42)
    # 强制 ext 是 png
    yande_data.file_ext = "png"

    task = fresh_store.recreate_task("fn-test", yande_data)
    assert task.file_name == "42.png"


# ---- integration: get_pending_task_ids sees recreated tasks ----

def test_recreate_task_makes_cancelled_task_visible_to_pending_query(fresh_store):
    """验证 recreate_task 的预期使用场景：cancelled → recreate → get_pending_task_ids 应看到"""
    yande_data = _make_yande_data(image_id=8888)

    # 模拟 cancelled 任务的 yande_data 已被清理（内存里没有这个 task）
    assert "cancelled-then-recreated" not in fresh_store._tasks

    # recreate 后，task 在内存里 status=PENDING
    fresh_store.recreate_task("cancelled-then-recreated", yande_data)
    assert fresh_store.get_pending_task_ids() == ["cancelled-then-recreated"]