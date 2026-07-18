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


# 终态集合：完成后从内存清除，DB 永久保留用于历史查询
_TERMINAL_STATUS = {
    TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED,
}


def _coerce_db_value(field: str, value):
    """Pydantic 字符串时间 → ORM datetime 转换"""
    if field in ("started_at", "completed_at") and isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return value


class TaskStore:
    """下载任务存储（内存缓存活跃任务 + DB 持久化终态）

    设计原则：
    - 活跃任务（pending/downloading/paused）在内存中，UI 实时读取
    - DB 写入仅在状态变化时触发，进度上报不落 DB
    - 终态任务从内存清除，DB 永久保留用于历史查询
    - 进程启动时从 DB 恢复 pending/paused 任务到内存
    """

    class ProgressData(BaseModel):
        """任务进度数据"""

        task_id: str = Field(..., description="任务ID")
        status: TaskStatus = Field(TaskStatus.PENDING, description="任务状态")
        progress: float = Field(0.0, description="进度")
        downloaded_size: int = Field(0, description="已下载大小")
        speed: float = Field(0.0, description="下载速度")
        file_size: Optional[int] = Field(None, description="总大小")

    class DownloadTask(ProgressData):
        image_id: int = Field(0, description="yande 图片 ID")
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

    def load_from_db(self) -> int:
        """进程启动时恢复活跃任务到内存缓存

        步骤：
        1. 崩溃恢复：把上次崩溃时残留的 downloading 任务改为 pending
        2. 拉取 pending/paused 任务到内存缓存
        """
        from src.dao.download_task_dao import download_task_dao

        # 1. 崩溃恢复
        with download_task_dao as dao:
            recovered = dao.recover_downloading_tasks()

        # 2. 加载活跃任务
        with download_task_dao as dao:
            active = dao.list_active()

        loaded = 0
        with self._lock:
            for rec in active:
                status = (
                    rec.status
                    if isinstance(rec.status, TaskStatus)
                    else TaskStatus(rec.status)
                )
                task = TaskStore.DownloadTask(
                    task_id=rec.task_id,
                    image_id=rec.image_id,
                    file_name=rec.file_name,
                    file_size=rec.file_size,
                    downloaded_size=rec.downloaded_size or 0,
                    progress=rec.progress or 0.0,
                    speed=0.0,
                    status=status,
                    error_message=rec.error_message,
                    started_at=rec.started_at.isoformat() if rec.started_at else None,
                    completed_at=rec.completed_at.isoformat() if rec.completed_at else None,
                    created_at=rec.created_at.isoformat() if rec.created_at else "",
                )
                self._tasks[rec.task_id] = task
                loaded += 1

        logger.info(
            f"TaskStore: 从 DB 恢复 {loaded} 个活跃任务到内存缓存"
            + (f"（崩溃恢复 {recovered} 个）" if recovered else "")
        )
        return loaded

    def create_task(self, task_id: str, yande_data: YandeData) -> dict:
        from src.dao.download_task_dao import download_task_dao

        file_name = f"{yande_data.id}.{yande_data.file_ext or 'jpg'}"
        file_size = yande_data.file_size

        # 先写 DB
        with download_task_dao as dao:
            dao.create(task_id, yande_data.id, file_name, file_size)

        # 再写内存
        with self._lock:
            task = TaskStore.DownloadTask(
                task_id=task_id,
                image_id=yande_data.id,
                yande_data=yande_data,
                file_name=file_name,
                file_size=file_size,
            )
            self._tasks[task_id] = task
            return task

    def recreate_task(self, task_id: str, yande_data: YandeData) -> "TaskStore.DownloadTask":
        """重建内存中的 cancelled 任务（用于重试）。

        cancelled 任务被 TaskStore.update_task 的终态清理逻辑移出 self._tasks，
        而 get_task 的 DB fallback 路径不会携带 yande_data。重试时调用本方法
        把 yande_data 重新注入内存，使 worker 能正常执行下载。

        不写 DB — DB 中 task 记录已存在；只重建内存缓存。
        """
        with self._lock:
            task = TaskStore.DownloadTask(
                task_id=task_id,
                image_id=yande_data.id,
                yande_data=yande_data,
                file_name=f"{yande_data.id}.{yande_data.file_ext or 'jpg'}",
                file_size=yande_data.file_size,
                # 进度字段保持默认（0），cancelled 重试语义：从头下载
            )
            self._tasks[task_id] = task
            return task

    def get_pending_task_ids(self) -> List[str]:
        """返回内存中所有 PENDING 状态的 task_id（lifecycle 重启恢复时使用）

        PAUSED 任务不返回 — 用户显式暂停的，重启不应偷偷启动。
        """
        with self._lock:
            return [
                tid for tid, t in self._tasks.items()
                if t.status == TaskStatus.PENDING
            ]

    def get_task(self, task_id: str) -> Optional[TaskStore.DownloadTask]:
        # 内存优先（活跃任务）
        with self._lock:
            task = self._tasks.get(task_id)
            if task:
                return task
        # 内存未命中：查 DB（终态/历史任务场景）
        from src.dao.download_task_dao import download_task_dao
        with download_task_dao as dao:
            rec = dao.get_by_id(task_id)
            if not rec:
                return None
            return TaskStore.DownloadTask(
                task_id=rec.task_id,
                image_id=rec.image_id,
                file_name=rec.file_name,
                file_size=rec.file_size,
                downloaded_size=rec.downloaded_size or 0,
                progress=rec.progress or 0.0,
                speed=0.0,
                status=(
                    rec.status
                    if isinstance(rec.status, TaskStatus)
                    else TaskStatus(rec.status)
                ),
                error_message=rec.error_message,
                started_at=rec.started_at.isoformat() if rec.started_at else None,
                completed_at=rec.completed_at.isoformat() if rec.completed_at else None,
                created_at=rec.created_at.isoformat() if rec.created_at else "",
            )

    def get_tasks(
        self, status: Optional[TaskStatus] = None, page: int = 1, page_size: int = 20
    ) -> tuple[List[dict], int]:
        """列表查询：DB 为主，活跃任务用内存实时进度覆盖

        背景：commit 38914a3 把 list 查询改为只走 DB，导致 downloading 任务的
        progress/speed/downloaded_size 永远 stale（progress_callback 只更新内存）。
        修复策略：DB 提供完整记录（含终态），内存提供活跃任务实时进度。
        终态任务（completed/failed/cancelled）不在内存中，DB 值已是权威。
        """
        from src.dao.download_task_dao import download_task_dao
        with download_task_dao as dao:
            db_tasks, db_total = dao.query(
                status=status, page=page, page_size=page_size
            )

        # 仅当查询涉及活跃状态时合并内存进度
        ACTIVE_STATUSES = {TaskStatus.PENDING, TaskStatus.DOWNLOADING, TaskStatus.PAUSED}
        query_active = status is None or status in ACTIVE_STATUSES

        if query_active:
            with self._lock:
                overrides = {
                    t.task_id: {
                        "progress": t.progress,
                        "speed": t.speed,
                        "downloaded_size": t.downloaded_size,
                    }
                    for t in self._tasks.values()
                }
            for task_dict in db_tasks:
                if task_dict["task_id"] in overrides:
                    task_dict.update(overrides[task_dict["task_id"]])

        return db_tasks, db_total

    def update_task(self, task_id: str, updates: dict):
        """更新任务：内存立即更新，DB 仅在状态变化时写入

        DB 写入采用"快照"模式：状态变化时把内存中已有进度字段一并落 DB，
        保证 DB 与内存在该时刻完全一致。
        """
        from src.dao.download_task_dao import download_task_dao

        db_payload = None
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                # 已从内存清除（终态），DB 已持久化，无需再写
                return

            # 1. 内存立即更新
            for key, value in updates.items():
                if hasattr(task, key):
                    setattr(task, key, value)

            # 2. DB 写入条件：本次 updates 包含 status 字段
            #    （progress_callback 不含 status，所以不会写 DB）
            if "status" in updates:
                # 快照：把内存中已有进度字段一并落 DB，保证一致性
                db_payload = {}
                for field in (
                    "status", "error_message", "started_at", "completed_at",
                    "downloaded_size", "progress", "speed",
                ):
                    value = getattr(task, field, None)
                    if value is not None:
                        db_payload[field] = _coerce_db_value(field, value)

                # 终态：从内存清除（DB 永久保留）
                if task.status in _TERMINAL_STATUS:
                    self._tasks.pop(task_id, None)

        if db_payload:
            with download_task_dao as dao:
                dao.update(task_id, **db_payload)

    def delete_task(self, task_id: str) -> bool:
        """删除任务：内存 + DB 双删"""
        from src.dao.download_task_dao import download_task_dao
        with self._lock:
            removed = self._tasks.pop(task_id, None) is not None
        with download_task_dao as dao:
            db_removed = dao.delete(task_id)
        return removed or db_removed


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

            def progress_callback(chunk_bytes: int):
                # 单位统一：所有 size 字段以字节（int）存储，避免浮点累加误差
                nonlocal \
                    downloaded_size, \
                    last_update_time, \
                    last_downloaded_size, \
                    download_speed
                current_time = time.time()
                downloaded_size += chunk_bytes
                time_diff = current_time - last_update_time
                if time_diff >= 0.5:
                    size_diff = downloaded_size - last_downloaded_size
                    download_speed = size_diff / time_diff if time_diff > 0 else 0
                    last_downloaded_size = downloaded_size
                    last_update_time = current_time
                    if file_size > 0:
                        progress = min(downloaded_size / file_size, 1.0)
                        task_store.update_task(
                            task_id,
                            {
                                "downloaded_size": downloaded_size,
                                "progress": progress,
                                "speed": download_speed,
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
                    "downloaded_size": file_size,
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
