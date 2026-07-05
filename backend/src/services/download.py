"""
下载业务逻辑层
"""

import uuid
from typing import List, Optional, Tuple

from loguru import logger

from src.common.constant import TaskStatus
from src.common.settings import config
from src.dao.yande_data_dao import YandeDataRepository
from src.infrastructure.download_queue import TaskStore, task_store, download_queue


class DownloadService:
    """下载服务类"""

    @staticmethod
    async def create_task(image_id: int) -> str:
        """
        创建下载任务

        Args:
            image_id: 图片ID

        Returns:
            任务 ID
        """
        with YandeDataRepository() as repo:
            yande_data = repo.get_by_id(image_id)

        if not yande_data:
            raise ValueError(f"Image {image_id} not found in database")

        task_id = str(uuid.uuid4())
        task_store.create_task(task_id, yande_data)
        await download_queue.add_task(task_id)
        return task_id

    @staticmethod
    async def create_batch_tasks(image_ids: List[int]) -> List[str]:
        """
        批量创建下载任务

        Args:
            image_ids: 图片ID列表

        Returns:
            任务 ID 列表
        """
        with YandeDataRepository() as repo:
            yande_data_map = {}
            for image_id in image_ids:
                data = repo.get_by_id(image_id)
                if data:
                    yande_data_map[image_id] = data

        task_ids = []
        for image_id in image_ids:
            if image_id not in yande_data_map:
                logger.warning(f"Image {image_id} not found in database, skipping task creation")
                continue
            task_id = str(uuid.uuid4())
            task_store.create_task(task_id, yande_data_map[image_id])
            await download_queue.add_task(task_id)
            task_ids.append(task_id)
        return task_ids

    @staticmethod
    def get_tasks(
        status_list: Optional[List[TaskStatus]] = None,
        sort_by: str = "created_at",
        order: str = "desc",
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[dict], int]:
        """
        获取任务列表（多状态过滤 + 排序 + 分页，DB 持久化）

        DB 查询为主，活跃任务用内存实时进度覆盖。
        progress_callback 只更新内存（不写 DB），所以 downloading 任务的
        progress/speed/downloaded_size 需要从内存合并。

        Args:
            status_list: 状态过滤列表；None/[] 表示所有
            sort_by: 排序字段（created_at/updated_at/completed_at/progress）
            order: 'asc' | 'desc'
            page: 页码
            page_size: 每页数量

        Returns:
            (任务列表, 总数)
        """
        from src.dao.download_task_dao import download_task_dao
        tasks, total = download_task_dao.query_tasks(
            status_list=status_list,
            sort_by=sort_by,
            order=order,
            page=page,
            page_size=page_size,
        )

        # 仅当查询涉及活跃状态时，用内存中实时进度覆盖 DB 快照
        ACTIVE_STATUSES = {TaskStatus.PENDING, TaskStatus.DOWNLOADING, TaskStatus.PAUSED}
        query_active = (
            status_list is None or not status_list
            or any(s in ACTIVE_STATUSES for s in status_list)
        )

        if query_active:
            with task_store._lock:
                overrides = {
                    t.task_id: {
                        "progress": t.progress,
                        "speed": t.speed,
                        "downloaded_size": t.downloaded_size,
                    }
                    for t in task_store._tasks.values()
                }
            for task_dict in tasks:
                if task_dict["task_id"] in overrides:
                    task_dict.update(overrides[task_dict["task_id"]])

        return tasks, total

    @staticmethod
    def get_status_counts() -> dict:
        """获取各状态任务数量（DB GROUP BY）"""
        from src.dao.download_task_dao import download_task_dao
        return download_task_dao.count_by_status()

    @staticmethod
    def get_task(task_id: str) -> Optional[TaskStore.DownloadTask]:
        """获取单个任务"""
        return task_store.get_task(task_id)

    @staticmethod
    def get_task_progress(task_id: str) -> Optional[TaskStore.ProgressData]:
        """获取任务进度"""
        task = task_store.get_task(task_id)
        if not task:
            return None
        return task

    @staticmethod
    async def start_task(task_id: str) -> Tuple[bool, str]:
        """
        启动任务

        Args:
            task_id: 任务 ID

        Returns:
            (成功与否, 消息)
        """
        task = task_store.get_task(task_id)
        if not task:
            return False, "任务不存在"

        # 终态任务（FAILED/CANCELLED）：内存已被终态清理，
        # get_task 的 DB fallback 路径返回的 task 不带 yande_data，
        # 必须从 yande_data 表重建内存缓存，否则 worker 会命中
        # run_download_async 的 'No yande_data' 错误。
        # 内存中仍带 yande_data 的任务（罕见的并发场景）跳过重建，避免覆盖。
        if task.yande_data is None and task.status in (
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        ):
            from src.dao.download_task_dao import download_task_dao
            from src.dao.yande_data_dao import YandeDataRepository
            with download_task_dao as dao:
                rec = dao.get_by_id(task_id)
            if not rec:
                return False, "任务记录不存在"
            with YandeDataRepository() as repo:
                yande_data = repo.get_by_id(rec.image_id)
            if not yande_data:
                return False, "图片元数据已丢失，无法重试"
            task_store.recreate_task(task_id, yande_data)
            # 重建后 task 仍是旧 DB fallback 的实例，需要重新从内存获取
            # 以便后续 status 检查和 update_task 走正确的内存对象
            task = task_store._tasks.get(task_id)

        if task.status not in [
            TaskStatus.PENDING,
            TaskStatus.PAUSED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        ]:
            return False, "任务无法启动"

        # 先改 status=PENDING 再 add_task，worker 拿起来时短路检查（run_download_async
        # 的 CANCELLED 短路）会自动放行，不会被误判为 cancelled 而跳过
        task_store.update_task(task_id, {"status": TaskStatus.PENDING})
        await download_queue.add_task(task_id)
        return True, "任务已启动"

    @staticmethod
    def pause_task(task_id: str) -> Tuple[bool, str]:
        """
        暂停任务

        Args:
            task_id: 任务 ID

        Returns:
            (成功与否, 消息)
        """
        task = task_store.get_task(task_id)
        if not task:
            return False, "任务不存在"
        if task.status != TaskStatus.DOWNLOADING:
            return False, "任务无法暂停"

        task_store.update_task(task_id, {"status": TaskStatus.PAUSED})
        return True, "任务已暂停"

    @staticmethod
    async def resume_task(task_id: str) -> Tuple[bool, str]:
        """
        恢复任务

        Args:
            task_id: 任务 ID

        Returns:
            (成功与否, 消息)
        """
        task = task_store.get_task(task_id)
        if not task:
            return False, "任务不存在"
        if task.status != TaskStatus.PAUSED:
            return False, "任务无法恢复"

        task_store.update_task(task_id, {"status": TaskStatus.PENDING})
        await download_queue.add_task(task_id)
        return True, "任务已恢复"

    @staticmethod
    def cancel_task(task_id: str) -> Tuple[bool, str]:
        """
        取消任务

        Args:
            task_id: 任务 ID

        Returns:
            (成功与否, 消息)
        """
        task = task_store.get_task(task_id)
        if not task:
            return False, "任务不存在"
        if task.status in [TaskStatus.COMPLETED, TaskStatus.CANCELLED]:
            return False, "任务无法取消"

        task_store.update_task(
            task_id,
            {"status": TaskStatus.CANCELLED, "completed_at": task.completed_at},
        )
        return True, "任务已取消"

    @staticmethod
    def delete_task(task_id: str) -> bool:
        """删除任务"""
        return task_store.delete_task(task_id)

    @staticmethod
    def get_download_history(
        page: int = 1, page_size: int = 20
    ) -> Tuple[List[dict], int]:
        """
        获取下载历史（TODO 下载完成的任务，从任务接口筛选的数据，待入数据库后与/task合并）

        Args:
            page: 页码
            page_size: 每页数量

        Returns:
            (已完成任务列表, 总数)
        """
        tasks, total = task_store.get_tasks(page=page, page_size=page_size)
        completed_tasks = [
            t
            for t in tasks
            if t["status"]
            in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]
        ]
        return completed_tasks, total

    @staticmethod
    def get_queue_status() -> dict:
        """获取队列状态"""
        return {
            "queue_size": download_queue.get_queue_size(),
            "max_concurrent": config.downloader.max_concurrent_tasks,
        }
