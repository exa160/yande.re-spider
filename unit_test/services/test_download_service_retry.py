"""DownloadService.start_task cancelled 重试分支测试

验证：
- CANCELLED 任务重试时：先从 DB 取 image_id，再从 yande_data 取元数据，
  调 task_store.recreate_task 重建内存 task，最后改 status=PENDING 并加入队列
- yande_data 缺失时返 False（防御：图片元数据丢失不能下载）
- allowlist 含 CANCELLED（允许 start_task 接受 cancelled 状态）
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]) + "/backend")

import pytest

from src.common.constant import TaskStatus
from src.dao.download_task_dao import DownloadTaskDao
from src.dao.yande_data_dao import YandeDataRepository
from src.infrastructure.download_queue import download_queue, task_store
from src.models.database.yande import DownloadTask, YandeData
from src.services.download import DownloadService


# ---- fixtures ----

@pytest.fixture
def reset_state():
    """每个用例前后清理单例状态，避免污染"""
    with task_store._lock:
        task_store._tasks.clear()
    try:
        asyncio.get_event_loop().run_until_complete(download_queue.stop())
    except Exception:
        pass
    yield
    try:
        asyncio.get_event_loop().run_until_complete(download_queue.stop())
    except Exception:
        pass
    with task_store._lock:
        task_store._tasks.clear()


def _seed_cancelled_task(task_id: str, image_id: int):
    """在 DB 中创建一条 cancelled 任务（模拟用户取消后的状态）。

    不注入内存 task_store — 模拟 cancel_task 触发的"终态从内存清除"。
    """
    with DownloadTaskDao() as dao:
        dao.create(task_id, image_id, f"{image_id}.jpg", file_size=1024)
        rec = dao.get_by_id(task_id)
        rec.status = TaskStatus.CANCELLED


def _seed_yande_data(image_id: int) -> None:
    """在 yande_data 表创建一条图片元数据，供 start_task 重试时查询"""
    with YandeDataRepository() as repo:
        repo.upsert(YandeData(
            id=image_id,
            file_ext="jpg",
            file_url=f"https://files.yande.re/sample/{image_id}.jpg",
            md5=None,
            file_size=1024,
        ))


# ---- 测试 ----

def test_start_task_cancelled_retry_rebuilds_memory_task(reset_state):
    """cancelled 任务重试：start_task 应重建内存 task（含 yande_data）并加入队列"""
    _seed_yande_data(image_id=60001)
    _seed_cancelled_task("retry-c-1", image_id=60001)

    # 内存里没有这个 task（模拟终态清理）
    assert "retry-c-1" not in task_store._tasks

    success, msg = asyncio.run(DownloadService.start_task("retry-c-1"))

    assert success, f"start_task 失败: {msg}"
    # 内存里现在有了，且 status=PENDING（已加入队列前改了状态）
    assert "retry-c-1" in task_store._tasks
    assert task_store._tasks["retry-c-1"].yande_data is not None
    assert task_store._tasks["retry-c-1"].status == TaskStatus.PENDING
    # 队列里也应该有
    assert download_queue._queue.qsize() >= 1


def test_start_task_cancelled_retry_yande_data_missing_returns_false(reset_state):
    """yande_data 缺失时（图片元数据被删除），重试返 False"""
    image_id = 60002
    # 不调用 _seed_yande_data — 模拟 yande_data 表里没有这个 image_id
    _seed_cancelled_task("retry-no-yande", image_id=image_id)

    success, msg = asyncio.run(DownloadService.start_task("retry-no-yande"))

    assert not success
    assert "元数据" in msg or "不存在" in msg


def test_start_task_cancelled_retry_download_record_missing_returns_false(reset_state):
    """DB 中 download_task 记录不存在时返 False（极端防御）"""
    # 不调用 _seed_cancelled_task — DB 中没有这条记录
    success, msg = asyncio.run(DownloadService.start_task("ghost-retry"))

    assert not success
    assert "不存在" in msg


def test_start_task_completed_still_rejected(reset_state):
    """COMPLETED 状态仍被拒绝（不在 allowlist 中）"""
    _seed_yande_data(image_id=60010)
    with DownloadTaskDao() as dao:
        dao.create("done-retry", 60010, "done.jpg", file_size=1024)
        rec = dao.get_by_id("done-retry")
        rec.status = TaskStatus.COMPLETED

    success, msg = asyncio.run(DownloadService.start_task("done-retry"))

    assert not success
    assert "无法启动" in msg


def test_start_task_downloading_still_rejected(reset_state):
    """DOWNLOADING 状态仍被拒绝（不在 allowlist 中）"""
    _seed_yande_data(image_id=60011)
    with DownloadTaskDao() as dao:
        dao.create("dl-retry", 60011, "dl.jpg", file_size=1024)
        rec = dao.get_by_id("dl-retry")
        rec.status = TaskStatus.DOWNLOADING

    success, msg = asyncio.run(DownloadService.start_task("dl-retry"))

    assert not success
    assert "无法启动" in msg