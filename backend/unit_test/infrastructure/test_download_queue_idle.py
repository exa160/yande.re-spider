"""DownloadQueue.get_idle_seconds：标签全量统计的算力门禁依据。

- 队列有待处理任务 / TaskStore 有 PENDING/DOWNLOADING → 0
- PAUSED 不算（用户暂停的任务可能长期不动）
- 否则返回距最后一次入队/任务结束的秒数
"""
import asyncio
import time

from src.common.constant import TaskStatus
from src.infrastructure.download_queue import TaskStore, download_queue, task_store


def _drain_queue() -> None:
    while not download_queue._queue.empty():
        download_queue._queue.get_nowait()
        download_queue._queue.task_done()


def test_idle_seconds_when_queue_and_store_empty():
    original = download_queue._last_activity
    try:
        download_queue._last_activity = time.monotonic() - 600
        assert download_queue.get_idle_seconds() >= 600
    finally:
        download_queue._last_activity = original


def test_queued_task_resets_idle_to_zero():
    original = download_queue._last_activity
    try:
        asyncio.run(download_queue.add_task("idle-test-queued"))
        assert download_queue.get_idle_seconds() == 0.0
    finally:
        _drain_queue()
        download_queue._last_activity = original


def test_pending_task_in_store_resets_idle_to_zero():
    original = download_queue._last_activity
    with task_store._lock:
        task_store._tasks["idle-test-pending"] = TaskStore.DownloadTask(
            task_id="idle-test-pending",
            image_id=1,
            file_name="1.jpg",
            status=TaskStatus.PENDING,
        )
    try:
        download_queue._last_activity = time.monotonic() - 600
        assert download_queue.get_idle_seconds() == 0.0
    finally:
        with task_store._lock:
            task_store._tasks.pop("idle-test-pending", None)
        download_queue._last_activity = original


def test_paused_task_does_not_block_idle():
    original = download_queue._last_activity
    with task_store._lock:
        task_store._tasks["idle-test-paused"] = TaskStore.DownloadTask(
            task_id="idle-test-paused",
            image_id=1,
            file_name="1.jpg",
            status=TaskStatus.PAUSED,
        )
    try:
        download_queue._last_activity = time.monotonic() - 600
        assert download_queue.get_idle_seconds() >= 600
    finally:
        with task_store._lock:
            task_store._tasks.pop("idle-test-paused", None)
        download_queue._last_activity = original
