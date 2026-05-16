from __future__ import annotations
import asyncio
import threading
import time
import hashlib
from datetime import datetime
from typing import Optional, List, Dict

from loguru import logger
from pydantic import BaseModel, ConfigDict, Field

from src.common import config, path_constant
from src.common.constant import TaskStatus
from src.dao.yande_data_dao import YandeDataRepository
from src.infrastructure.downloader import FileInfo, MultiDown
from src.models.database.yande import YandeData


class TaskStore:
    class ProgressData(BaseModel):
        """任务进度数据"""

        task_id: str = Field(..., description="任务ID")
        status: TaskStatus = Field(TaskStatus.PENDING, description="任务状态")
        progress: float = Field(0.0, description="进度")
        downloaded_size: int = Field(0, description="已下载大小")
        speed: float = Field(0.0, description="下载速度")
        file_size: Optional[int] = Field(None, description="总大小")

    class DownloadTask(ProgressData):
        yande_data: Optional[YandeData] = Field(None, description="yande数据")
        file_name: Optional[str] = Field(..., description="文件名")
        error_message: Optional[str] = Field(None, description="错误信息")
        started_at: Optional[str] = Field(None, description="开始时间")
        completed_at: Optional[str] = Field(None, description="完成时间")
        created_at: str = Field(default_factory=lambda: datetime.now().isoformat(), description="创建时间")
        # TODO sqlalchemy替换为sqlmodel
        model_config = ConfigDict(validate_assignment=True, arbitrary_types_allowed=True, from_attributes=True)


    def __init__(self):
        self._tasks: Dict[str, TaskStore.DownloadTask] = {}
        self._lock = threading.Lock()

    def create_task(self, task_id: str, yande_data: YandeData) -> dict:
        with self._lock:
            task = TaskStore.DownloadTask(
                task_id=task_id,
                yande_data=yande_data,
                file_name=f"{yande_data.id}.{yande_data.file_ext}",
                file_size=yande_data.file_size
            )
            self._tasks[task_id] = task
            return task

    def get_task(self, task_id: str) -> Optional[TaskStore.DownloadTask]:
        with self._lock:
            return self._tasks.get(task_id)

    def get_tasks(
        self, status: Optional[TaskStatus] = None, page: int = 1, page_size: int = 20
    ) -> tuple[List[dict], int]:
        with self._lock:
            tasks = list(self._tasks.values())
            if status:
                tasks = [t for t in tasks if t.status == status]
            tasks.sort(key=lambda x: x.created_at, reverse=True)
            total = len(tasks)
            start = (page - 1) * page_size
            end = start + page_size
            return [task.model_dump() for task in tasks[start:end]], total

    def update_task(self, task_id: str, updates: dict):
        with self._lock:
            task = self._tasks.get(task_id)
            if task:
                for key, value in updates.items():
                    if hasattr(task, key):
                        setattr(task, key, value)
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

    if task.status == TaskStatus.CANCELLED:
        return

    task_store.update_task(
        task_id,
        {"status": TaskStatus.DOWNLOADING, "started_at": datetime.now().isoformat()},
    )

    yande_data = task.yande_data

    try:
        if not yande_data:
            logger.error(f"No yande_data for task {task_id}")
            task_store.update_task(
                task_id, {"status": TaskStatus.FAILED, "error_message": "Missing yande_data"}
            )
            return

        file_url = yande_data.file_url
        file_ext = yande_data.file_ext or "jpg"
        image_id = yande_data.id
        expected_md5 = yande_data.md5
        file_size = yande_data.file_size or 0

        originals_dir = path_constant.originals_dir

        original_path = originals_dir / f"{image_id}.{file_ext}"

        download_failed = False
        error_message = None
        db_updated = False
        need_download = True
        if original_path.exists() and expected_md5:
            md5_hasher = hashlib.md5()
            with original_path.open("rb") as existing_file:
                for chunk in iter(lambda: existing_file.read(1024*1024), b""):
                    md5_hasher.update(chunk)
            file_md5 = md5_hasher.hexdigest()
            if file_md5 == expected_md5:
                logger.info(
                    f"Original exists and MD5 matches ({file_md5}), skipping download"
                )
                need_download = False
            else:
                logger.info(f"Original exists but MD5 mismatch, re-downloading")
                original_path.unlink()

        if need_download:
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
                    if file_size > 0:
                        progress = min(
                            downloaded_size / (file_size / 1024 / 1024), 1.0
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
            # 在线程池中执行同步下载代码，避免阻塞事件循环
            multi_down = await asyncio.to_thread(
                MultiDown,
                file_info=FileInfo(
                    url=file_url,
                    file_path=originals_dir,
                    file_name=f"{image_id}.{file_ext}",
                    file_size=file_size,
                    md5=expected_md5,
                ),
                _progress_callback=progress_callback,
            )
            try:
                await asyncio.to_thread(multi_down.start)
            except Exception as download_err:
                download_failed = True
                error_message = f"下载失败: {str(download_err)}"
                logger.error(f"Download failed for {task_id}: {download_err}")
            finally:
                await asyncio.to_thread(multi_down.cleanup)
        else:
            task_store.update_task(
                task_id,
                {
                    "status": TaskStatus.COMPLETED,
                    "error_message": "已下载",
                    "progress": 1.0,
                    "downloaded_size": file_size
                },
            )

        if download_failed:
            task_store.update_task(
                task_id,
                {
                    "status": TaskStatus.FAILED,
                    "error_message": error_message or "下载失败",
                    "completed_at": datetime.now().isoformat(),
                },
            )
            logger.warning(f"Download failed for image {image_id}: {error_message}")
        else:
            db_updated = await _update_image_database(yande_data, True)
            task_store.update_task(
                task_id,
                {
                    "yande_data": None,
                    "status": TaskStatus.COMPLETED,
                    "progress": 1.0,
                    "completed_at": datetime.now().isoformat(),
                },
            )
        if not db_updated:
            logger.warning(f"Database update skipped for image {image_id}")
    except Exception as e:
        task_store.update_task(
            task_id, {"status": TaskStatus.FAILED, "error_message": str(e)}
        )


async def _update_image_database(yande_data: YandeData, down_flag: bool) -> bool:
    try:
        with YandeDataRepository() as repo:
            image_id = yande_data.id
            updated = repo.update_down_flag(image_id, down_flag)

            if not updated:
                repo.upsert(yande_data)
                logger.info(f"Image {image_id} inserted via yande_data")
            else:
                logger.info(f"Image {image_id} down_flag updated")

        return True
    except Exception as db_err:
        logger.error(f"Failed to update database: {db_err}")
        return False


download_queue = DownloadQueue()
