"""DownloadLifecycle.lifespan 重启恢复测试（pending 任务自动加入队列）

验证：
- load_from_db 恢复的 PENDING 任务会被加入 download_queue
- PAUSED 任务不会被自动启动（用户显式暂停的，重启不应偷偷启动）
- lifecycle 启动顺序：load_from_db → 入队 → start

注意：mock download_queue.start 防止 worker 启动后立即消费队列
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]) + "/backend")

import pytest

from src.common.constant import TaskStatus
from src.dao.download_task_dao import DownloadTaskDao
from src.infrastructure.download_queue import download_queue, task_store
from src.lifecycle.download import DownloadLifecycle
from src.models.database.yande import DownloadTask


# ---- fixtures ----

@pytest.fixture
def noop_queue_start(monkeypatch):
    """mock download_queue.start：测试只关心入队，不真正启动 worker
    （worker 启动后会立即消费队列里的 task_id，无法观察到 qsize）"""
    async def noop(num_workers=3):
        pass
    monkeypatch.setattr(download_queue, "start", noop)
    yield


@pytest.fixture
def reset_state():
    """每个用例前后清理 task_store 内存缓存 + download_tasks DB 表 + download_queue"""
    from src.models.database.yande import DownloadTask as DTModel

    def _cleanup():
        with task_store._lock:
            task_store._tasks.clear()
        with DownloadTaskDao() as dao:
            dao.session.query(DTModel).delete()
        # 清空 asyncio.Queue 里残留的 task_id（单例队列跨测试残留）
        while not download_queue._queue.empty():
            try:
                download_queue._queue.get_nowait()
            except Exception:
                break

    _cleanup()
    yield
    _cleanup()


def _seed_pending_task(task_id: str, image_id: int, status: TaskStatus = TaskStatus.PENDING):
    """在 DB 中创建一条任务记录并直接注入内存（模拟 load_from_db 后的状态）"""
    with DownloadTaskDao() as dao:
        dao.create(task_id, image_id, f"{image_id}.jpg", file_size=1024)
        rec = dao.get_by_id(task_id)
        rec.status = status

    # 模拟 TaskStore.load_from_db 已经把它加载到内存
    with task_store._lock:
        from src.infrastructure.download_queue import TaskStore
        task = TaskStore.DownloadTask(
            task_id=task_id,
            file_name=f"{image_id}.jpg",
            file_size=1024,
        )
        task.status = status
        task_store._tasks[task_id] = task


# ---- 测试 ----

def test_lifespan_adds_pending_tasks_to_queue(reset_state, noop_queue_start):
    """lifespan 启动时，DB 中 PENDING 任务被加入 download_queue"""
    _seed_pending_task("lifecycle-1", image_id=50001, status=TaskStatus.PENDING)
    _seed_pending_task("lifecycle-2", image_id=50002, status=TaskStatus.PENDING)

    async def run():
        async with DownloadLifecycle.lifespan(None):
            await asyncio.sleep(0.05)
            return download_queue._queue.qsize()

    qsize = asyncio.run(run())

    assert qsize == 2, f"期望队列里有 2 个 pending，实际 {qsize}"


def test_lifespan_does_not_add_paused_tasks(reset_state, noop_queue_start):
    """lifespan 启动时，PAUSED 任务不被自动加入队列"""
    _seed_pending_task("paused-1", image_id=50010, status=TaskStatus.PAUSED)
    _seed_pending_task("pending-1", image_id=50011, status=TaskStatus.PENDING)

    async def run():
        async with DownloadLifecycle.lifespan(None):
            await asyncio.sleep(0.05)
            return download_queue._queue.qsize()

    qsize = asyncio.run(run())
    assert qsize == 1, f"期望队列只有 1 个 pending，实际 {qsize}（paused 不应被加入）"


def test_lifespan_no_pending_tasks_empty_queue(reset_state, noop_queue_start):
    """没有 pending 任务时队列为空（不报错）"""
    _seed_pending_task("done-1", image_id=50020, status=TaskStatus.COMPLETED)

    async def run():
        async with DownloadLifecycle.lifespan(None):
            await asyncio.sleep(0.05)
            return download_queue._queue.qsize()

    qsize = asyncio.run(run())
    assert qsize == 0


def test_lifespan_only_runs_add_for_pending(reset_state, noop_queue_start, monkeypatch):
    """lifespan 不应该对 PAUSED/COMPLETED/FAILED 任务调 add_task"""
    add_task_calls = []

    async def spy_add_task(task_id):
        add_task_calls.append(task_id)

    monkeypatch.setattr(download_queue, "add_task", spy_add_task)

    _seed_pending_task("p-only", image_id=50100, status=TaskStatus.PENDING)
    _seed_pending_task("pa-only", image_id=50101, status=TaskStatus.PAUSED)

    async def run():
        async with DownloadLifecycle.lifespan(None):
            await asyncio.sleep(0.05)

    asyncio.run(run())

    assert add_task_calls == ["p-only"], f"期望只调一次 add_task，实际 {add_task_calls}"