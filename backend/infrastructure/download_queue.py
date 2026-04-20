import asyncio
import threading
import time
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict

from loguru import logger

from backend.config.settings import config


class TaskStatus(str, Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskStore:
    def __init__(self):
        self._tasks: Dict[str, Dict] = {}
        self._lock = threading.Lock()

    def create_task(self, task_id: str, task_data: dict) -> dict:
        with self._lock:
            self._tasks[task_id] = {
                "task_id": task_id,
                "image_id": task_data["image_id"],
                "file_url": task_data["file_url"],
                "save_path": task_data["save_path"],
                "file_name": task_data["file_name"],
                "thread_num": task_data.get("thread_num", 4),
                "status": TaskStatus.PENDING,
                "progress": 0.0,
                "downloaded_size": 0,
                "total_size": task_data.get("total_size", 0),
                "speed": 0.0,
                "error_message": None,
                "created_at": datetime.now().isoformat(),
                "started_at": None,
                "completed_at": None,
                "tags": task_data.get("tags"),
                "width": task_data.get("width"),
                "height": task_data.get("height"),
                "rating": task_data.get("rating"),
                "author": task_data.get("author"),
                "md5": task_data.get("md5"),
            }
            return self._tasks[task_id]

    def get_task(self, task_id: str) -> Optional[dict]:
        with self._lock:
            return self._tasks.get(task_id)

    def get_tasks(
        self, status: Optional[TaskStatus] = None, page: int = 1, page_size: int = 20
    ) -> tuple[List[dict], int]:
        with self._lock:
            tasks = list(self._tasks.values())
            if status:
                tasks = [t for t in tasks if t["status"] == status]
            tasks.sort(key=lambda x: x["created_at"], reverse=True)
            total = len(tasks)
            start = (page - 1) * page_size
            end = start + page_size
            return tasks[start:end], total

    def update_task(self, task_id: str, updates: dict):
        with self._lock:
            if task_id in self._tasks:
                self._tasks[task_id].update(updates)

    def delete_task(self, task_id: str) -> bool:
        with self._lock:
            if task_id in self._tasks:
                del self._tasks[task_id]
                return True
            return False


task_store = TaskStore()


class DownloadQueue:
    def __init__(self):
        self._queue: asyncio.Queue = asyncio.Queue()
        self._workers: List[asyncio.Task] = []
        self._running = False
        self._max_concurrent = 3

    def _get_max_concurrent(self) -> int:
        return config.downloader.max_concurrent_tasks

    async def _worker(self, worker_id: int):
        while self._running:
            try:
                task_id = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            if not self._running:
                self._queue.put_nowait(task_id)
                break

            semaphore = asyncio.Semaphore(self._get_max_concurrent())
            async with semaphore:
                await run_download_async(task_id)
            self._queue.task_done()

    async def start(self, num_workers: int = 3):
        if self._running:
            return
        self._running = True
        self._workers = [
            asyncio.create_task(self._worker(i)) for i in range(num_workers)
        ]
        logger.info(f"Download queue started with {num_workers} workers")

    async def stop(self):
        self._running = False
        for worker in self._workers:
            worker.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers = []
        logger.info("Download queue stopped")

    async def add_task(self, task_id: str):
        await self._queue.put(task_id)
        logger.debug(f"Task {task_id} added to queue")

    def get_queue_size(self) -> int:
        return self._queue.qsize()

    def get_active_count(self) -> int:
        return sum(1 for w in self._workers if not w.done())


download_queue = DownloadQueue()


async def run_download_async(task_id: str):
    from backend.infrastructure.downloader import MultiDown
    from backend.config.constant import ORIGINALS_DIR, PREVIEWS_DIR

    task = task_store.get_task(task_id)
    if not task:
        return

    if task["status"] == TaskStatus.CANCELLED:
        return

    task_store.update_task(
        task_id,
        {"status": TaskStatus.DOWNLOADING, "started_at": datetime.now().isoformat()},
    )

    try:
        import os
        import hashlib
        from pathlib import Path

        ORIGINALS_DIR.mkdir(parents=True, exist_ok=True)
        PREVIEWS_DIR.mkdir(parents=True, exist_ok=True)

        file_ext = (
            task["file_name"].rsplit(".", 1)[-1] if "." in task["file_name"] else "jpg"
        )
        original_path = ORIGINALS_DIR / f"{task['image_id']}.{file_ext}"

        expected_md5 = task.get("md5")
        need_download = True
        download_failed = False
        error_message = None

        if original_path.exists() and expected_md5:
            file_md5 = hashlib.md5(open(original_path, "rb").read()).hexdigest()
            if file_md5 == expected_md5:
                logger.info(
                    f"Original exists and MD5 matches ({file_md5}), skipping download"
                )
                need_download = False
            else:
                logger.info(f"Original exists but MD5 mismatch, re-downloading")
                original_path.unlink()

        if need_download:
            total_size = task.get("total_size", 0)
            downloaded_size = 0
            last_update_time = time.time()
            last_downloaded_size = 0
            download_speed = 0.0
            progress_lock = asyncio.Lock()

            def progress_callback(chunk_mb: float):
                nonlocal \
                    downloaded_size, \
                    last_update_time, \
                    last_downloaded_size, \
                    download_speed
                current_time = time.time()
                downloaded_size += chunk_mb
                time_diff = current_time - last_update_time
                if time_diff >= 0.5:
                    size_diff = downloaded_size - last_downloaded_size
                    download_speed = size_diff / time_diff if time_diff > 0 else 0
                    last_downloaded_size = downloaded_size
                    last_update_time = current_time
                    if total_size > 0:
                        progress = min(
                            downloaded_size / (total_size / 1024 / 1024), 1.0
                        )
                        task_store.update_task(
                            task_id,
                            {
                                "downloaded_size": int(downloaded_size * 1024 * 1024),
                                "progress": progress,
                                "speed": download_speed
                                * 1024
                                * 1024,  # Convert MB/s to bytes/s
                            },
                        )

            try:
                # 在线程池中执行同步下载代码，避免阻塞事件循环
                await asyncio.to_thread(
                    MultiDown,
                    url=task["file_url"],
                    file_path=str(ORIGINALS_DIR),
                    file_name=f"{task['image_id']}.{file_ext}",
                    file_size=total_size,
                    _md5=task.get("md5"),
                    _id=task["image_id"],
                    _show_progress=False,
                    _progress_callback=progress_callback,
                )
            except Exception as download_err:
                download_failed = True
                error_message = f"下载失败: {str(download_err)}"
                logger.error(f"Download failed for {task_id}: {download_err}")

        preview_url = task.get("preview_url")
        if preview_url:
            preview_path = PREVIEWS_DIR / f"{task['image_id']}.{file_ext}"
            if not preview_path.exists():
                try:
                    import requests

                    proxies = (
                        config.yande_api.proxies if config.yande_api.proxies else None
                    )
                    # 在线程池中执行同步下载代码
                    resp = await asyncio.to_thread(
                        requests.get, preview_url, proxies=proxies, timeout=10
                    )
                    if resp.status_code == 200:
                        with open(preview_path, "wb") as f:
                            f.write(resp.content)
                        logger.info(f"Preview downloaded: {preview_path}")
                except Exception as e:
                    logger.warning(f"Failed to download preview: {e}")

        try:
            from backend.dao.database import MariaDBClient
            from backend.models.yande import Rating
            from datetime import datetime as dt

            client = MariaDBClient()
            if not client.update_down_flag(task["image_id"], True):
                rating_str = task.get("rating", "s")
                if rating_str in ["Safe", "s", "S"]:
                    rating = Rating.S.value
                elif rating_str in ["Questionable", "q", "Q"]:
                    rating = Rating.R15.value
                else:
                    rating = Rating.R18.value

                file_ext = (
                    task.get("file_name", "jpg").rsplit(".", 1)[-1]
                    if "." in task.get("file_name", "jpg")
                    else "jpg"
                )

                new_record = client.YandeData(
                    id=task["image_id"],
                    tags=task.get("tags", ""),
                    created_at=dt.now(),
                    updated_at=dt.now(),
                    creator_id=None,
                    author=task.get("author", ""),
                    change=0,
                    source=task["file_url"],
                    score=0,
                    md5=task.get("md5", ""),
                    file_size=task.get("total_size", 0),
                    file_ext=file_ext,
                    file_url=task["file_url"],
                    is_shown_in_index=True,
                    preview_url=task["file_url"].replace("images", "previews"),
                    width=task.get("width", 0),
                    height=task.get("height", 0),
                    rating=rating,
                    is_rating_locked=False,
                    has_children=False,
                    parent_id=None,
                    status="active",
                    is_pending=False,
                    is_held=False,
                    down_flag=True,
                )
                client.insert_data(new_record)
            client.close()
        except Exception as db_err:
            logger.error(f"Failed to update database: {db_err}")

        if download_failed:
            task_store.update_task(
                task_id,
                {
                    "status": TaskStatus.FAILED,
                    "error_message": error_message or "下载失败",
                    "completed_at": datetime.now().isoformat(),
                },
            )
        else:
            task_store.update_task(
                task_id,
                {
                    "status": TaskStatus.COMPLETED,
                    "progress": 1.0,
                    "completed_at": datetime.now().isoformat(),
                },
            )
    except Exception as e:
        task_store.update_task(
            task_id, {"status": TaskStatus.FAILED, "error_message": str(e)}
        )
