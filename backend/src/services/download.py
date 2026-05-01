"""
下载业务逻辑层
"""

import uuid
from typing import List, Optional, Tuple

from src.infrastructure.download_queue import task_store, download_queue
from src.common.constant import TaskStatus
from src.common.settings import config


class DownloadService:
    """下载服务类"""

    @staticmethod
    async def create_task(task_data: dict) -> str:
        """
        创建下载任务

        Args:
            task_data: 任务数据

        Returns:
            任务 ID
        """
        task_id = str(uuid.uuid4())
        task_store.create_task(task_id, task_data)
        await download_queue.add_task(task_id)
        return task_id

    @staticmethod
    async def create_batch_tasks(tasks_data: List[dict]) -> List[str]:
        """
        批量创建下载任务

        Args:
            tasks_data: 任务数据列表

        Returns:
            任务 ID 列表
        """
        task_ids = []
        for task_data in tasks_data:
            task_id = str(uuid.uuid4())
            task_store.create_task(task_id, task_data)
            await download_queue.add_task(task_id)
            task_ids.append(task_id)
        return task_ids

    @staticmethod
    def get_tasks(
        status: Optional[TaskStatus] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[dict], int]:
        """
        获取任务列表

        Args:
            status: 任务状态过滤
            page: 页码
            page_size: 每页数量

        Returns:
            (任务列表, 总数)
        """
        return task_store.get_tasks(status, page, page_size)

    @staticmethod
    def get_task(task_id: str) -> Optional[dict]:
        """获取单个任务"""
        return task_store.get_task(task_id)

    @staticmethod
    def get_task_progress(task_id: str) -> Optional[dict]:
        """获取任务进度"""
        task = task_store.get_task(task_id)
        if not task:
            return None
        return {
            "task_id": task["task_id"],
            "status": task["status"],
            "progress": task["progress"],
            "downloaded_size": task["downloaded_size"],
            "total_size": task["total_size"],
            "speed": task.get("speed"),
        }

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
        if task["status"] not in [
            TaskStatus.PENDING,
            TaskStatus.PAUSED,
            TaskStatus.FAILED,
        ]:
            return False, "任务无法启动"

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
        if task["status"] != TaskStatus.DOWNLOADING:
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
        if task["status"] != TaskStatus.PAUSED:
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
        if task["status"] in [TaskStatus.COMPLETED, TaskStatus.CANCELLED]:
            return False, "任务无法取消"

        task_store.update_task(
            task_id,
            {"status": TaskStatus.CANCELLED, "completed_at": task["completed_at"]},
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
