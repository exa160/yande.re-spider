import asyncio
import threading
import time
from datetime import datetime
from typing import Optional, List, Dict

import requests
from loguru import logger

from src.common import config, path_constant
from src.common.constant import TaskStatus
from src.common.utils import get_proxy
from src.dao.yande_data import YandeDataRepository
from src.infrastructure.downloader import MultiDown


class TaskStore:
    # 任务字段映射配置: 外部字段名 -> 内部字段名 (None 表示同名)
    TASK_FIELD_MAPPING = {
        "image_id": "image_id",
        "file_url": "file_url",
        "save_path": "save_path",
        "file_name": "file_name",
        "thread_num": "thread_num",
        "total_size": "total_size",
        "tags": "tags",
        "width": "width",
        "height": "height",
        "rating": "rating",
        "author": "author",
        "md5": "md5",
    }

    # 内部任务默认值
    TASK_DEFAULTS = {
        "status": TaskStatus.PENDING,
        "progress": 0.0,
        "downloaded_size": 0,
        "speed": 0.0,
        "error_message": None,
        "started_at": None,
        "completed_at": None,
    }

    def __init__(self):
        self._tasks: Dict[str, Dict] = {}
        self._lock = threading.Lock()

    def create_task(self, task_id: str, task_data: dict) -> dict:
        with self._lock:
            # 从映射配置构建任务数据
            task = {
                "task_id": task_id,
                "created_at": datetime.now().isoformat(),
            }

            # 应用字段映射
            for src_field, dest_field in self.TASK_FIELD_MAPPING.items():
                if src_field in task_data:
                    task[dest_field] = task_data[src_field]

            # 应用默认值
            task.update(self.TASK_DEFAULTS)

            # 处理默认值字段
            task["thread_num"] = task_data.get("thread_num", 4)
            task["total_size"] = task_data.get("total_size", 0)

            self._tasks[task_id] = task
            return task

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
            # TODO 更新数据库：目前只更新内存中的任务状态，后续需要增加数据库更新逻辑 --- IGNORE ---

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
        self._semaphore = asyncio.Semaphore(config.downloader.max_concurrent_tasks)

    async def _worker(self, worker_id: int):
        while self._running:
            try:
                task_id = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            if not self._running:
                self._queue.put_nowait(task_id)
                break

            async with self._semaphore:
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


async def run_download_async(task_id: str):
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
        import hashlib

        originals_dir = path_constant.originals_dir
        previews_dir = path_constant.previews_dir
        originals_dir.mkdir(parents=True, exist_ok=True)
        previews_dir.mkdir(parents=True, exist_ok=True)

        file_ext = (
            task["file_name"].rsplit(".", 1)[-1] if "." in task["file_name"] else "jpg"
        )
        original_path = originals_dir / f"{task['image_id']}.{file_ext}"

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
                multi_down = await asyncio.to_thread(
                    MultiDown,
                    url=task["file_url"],
                    file_path=str(originals_dir),
                    file_name=f"{task['image_id']}.{file_ext}",
                    file_size=total_size,
                    _md5=task.get("md5"),
                    _id=task["image_id"],
                    _progress_callback=progress_callback,
                )
                await asyncio.to_thread(multi_down.start)
            except Exception as download_err:
                download_failed = True
                error_message = f"下载失败: {str(download_err)}"
                logger.error(f"Download failed for {task_id}: {download_err}")

        preview_url = task.get("preview_url")
        if preview_url:
            preview_path = previews_dir / f"{task['image_id']}.{file_ext}"
            if not preview_path.exists():
                try:
                    # 在线程池中执行同步下载代码
                    resp = await asyncio.to_thread(
                        requests.get, preview_url, proxies= get_proxy(), timeout=10
                    )
                    if resp.status_code == 200:
                        with open(preview_path, "wb") as f:
                            f.write(resp.content)
                        logger.info(f"Preview downloaded: {preview_path}")
                except Exception as e:
                    logger.warning(f"Failed to download preview: {e}")

        

        if download_failed:
            task_store.update_task(
                task_id,
                {
                    "status": TaskStatus.FAILED,
                    "error_message": error_message or "下载失败",
                    "completed_at": datetime.now().isoformat(),
                },
            )
            # 更新数据库：下载失败时不更新 down_flag，只记录错误日志
            logger.warning(f"Download failed for image {task['image_id']}: {error_message}")
            db_updated = False
        else:
            # 更新数据库：下载成功，设置 down_flag=True
            db_updated = await _update_image_database(task, True)
            task_store.update_task(
                task_id,
                {
                    "status": TaskStatus.COMPLETED,
                    "progress": 1.0,
                    "completed_at": datetime.now().isoformat(),
                },
            )
        if not db_updated:
            logger.warning(f"Database update skipped for image {task['image_id']}")
    except Exception as e:
        task_store.update_task(
            task_id, {"status": TaskStatus.FAILED, "error_message": str(e)}
        )


async def _update_image_database(task: dict, down_flag: bool) -> bool:
    """
    更新图片数据库（down_flag 和记录）

    Args:
        task: 下载任务数据
        down_flag: 下载标志

    Returns:
        是否更新成功
    """
    try:
        with YandeDataRepository() as repo:
            # 尝试更新 down_flag
            updated = repo.update_down_flag(task["image_id"], down_flag)

            if not updated:
                # 记录不存在，使用 upsert 插入（与 query_yande_api 流程相似）
                # TODO: 任务信息不使用无效字段，图片入库信息以post.json接口传入数据为准，不用以下数据

                repo.upsert(task)
                logger.info(f"Image {task['image_id']} inserted via task data")
            else:
                logger.info(f"Image {task['image_id']} down_flag updated")

        return True
    except Exception as db_err:
        logger.error(f"Failed to update database: {db_err}")
        return False


download_queue = DownloadQueue()
