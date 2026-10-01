"""
下载业务逻辑层
"""

import uuid
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from loguru import logger
from sqlalchemy import select

from src.common.constant import TaskStatus
from src.common.settings import config
from src.dao.yande_data_dao import YandeDataRepository
from src.infrastructure.download_queue import TaskStore, task_store, download_queue
from src.models.database.yande import YandeData
from src.models.response.my_favorites import MyFavoritePreviewImage


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
        download_first: bool = False,
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
            download_first: 是否将 status='downloading' 的任务排在最前

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
            download_first=download_first,
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
    def get_image_states(finished_window: int = 30) -> dict:
        """图片下载状态快照（供前端把「下载中 / 已下载」标识与后端队列对齐）。

        背景：yande_data.down_flag 只在下载**完成**时才落库
        （见 download_queue._update_image_database），因此前端在下单瞬间
        无从得知「这张图正在下载」——收藏自动下载、单图/批量下载都表现为
        「点了没反应」。本方法把队列状态按 image_id 暴露出去：

        Args:
            finished_window: 终态回看窗口（秒）。任务刚结束的这段时间内
                仍会出现在 finished 里，前端据此把「下载中」收敛为
                「已下载」或复位。

        Returns:
            {
                "active": [{"image_id", "task_id", "status", "progress", "speed", "downloaded_size"}],
                "finished": [{"image_id", "status"}],
            }
            status 取值：pending / downloading / paused / completed / failed / cancelled
        """
        from src.dao.download_task_dao import DownloadTaskDao

        since = datetime.now() - timedelta(seconds=max(0, finished_window))

        with DownloadTaskDao() as dao:
            active_records = dao.active_states_by_image()
            finished_map = dao.finished_states_by_image(since)

        # DB 状态是权威的（状态变化必落库），但 progress/speed 只在内存里
        # 实时更新（progress_callback 不写 DB），需要按 task_id 从内存合并。
        with task_store._lock:
            memory = {t.task_id: t for t in task_store._tasks.values()}

        active = []
        for image_id, record in active_records.items():
            mem = memory.get(record.task_id)
            status = mem.status if mem else record.status
            active.append(
                {
                    "image_id": image_id,
                    "task_id": record.task_id,
                    "status": status.value if hasattr(status, "value") else status,
                    "progress": (mem.progress if mem else record.progress) or 0.0,
                    "speed": (mem.speed if mem else record.speed) or 0.0,
                    "downloaded_size": (
                        (mem.downloaded_size if mem else record.downloaded_size) or 0
                    ),
                }
            )

        finished = [
            {"image_id": image_id, "status": status}
            for image_id, status in finished_map.items()
        ]
        return {"active": active, "finished": finished}

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
            from src.dao.download_task_dao import DownloadTaskDao
            from src.dao.yande_data_dao import YandeDataRepository
            with DownloadTaskDao() as dao:
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

    # ============================================================
    # 「最近下载」功能（设计文档 2026-09-21-recent-downloads-design.md §3.1 / §3.2）
    #
    # 数据源统一为 download_task 表的 completed_at：yande_data 没有本地下载时间列，
    # 本期不改表结构（见设计文档 §2.1）。以下 3 个方法都只读/只删 status=COMPLETED
    # 且 completed_at 非空的任务记录，语义与 DAO 的 4 个方法严格一致。
    # ============================================================

    @staticmethod
    def list_completed_image_ids(
        page: int = 1, page_size: int = 20
    ) -> List[Tuple[int, datetime]]:
        """分页返回最近完成的下载任务对应的 (image_id, 最新完成时间)，时间倒序。

        Returns:
            [(image_id, latest_completed_at), ...]；重复下载同一张图只出现一次。
        """
        from src.dao.download_task_dao import DownloadTaskDao

        with DownloadTaskDao() as dao:
            return dao.list_completed_image_ids(page=page, page_size=page_size)

    @staticmethod
    def count_completed_images() -> int:
        """最近下载的**去重图片数**（COUNT(DISTINCT image_id)），用作磁贴角标。

        与 ``count_downloaded()``（随机浏览角标 = down_flag=True 总数）口径不同：
        重复下载同一张图只计一次，避免角标虚高。
        """
        from src.dao.download_task_dao import DownloadTaskDao

        with DownloadTaskDao() as dao:
            return dao.count_completed_distinct_images()

    @staticmethod
    def get_recent_preview(limit: int = 8) -> List[MyFavoritePreviewImage]:
        """最近下载的预览图元数据（按完成时间倒序），与角标口径一致。

        实现：先用 download_task 取出最近 limit 个去重 image_id（携带完成时间，
        天然倒序），再回表 yande_data 补齐 tags / rating 元数据，最后按任务侧
        的顺序重排（SQL IN 查询不保证顺序）。

        有意**不**按 ``down_flag=True`` 过滤：角标统计的是 download_task 的
        completed 记录，若预览再叠加一层 down_flag 过滤，会出现「角标 5 张但
        磁贴只显示 3 张」的自相矛盾。两者必须同源。

        已知取舍：用户手动删掉下载任务记录后该图会从预览中消失，但磁盘文件
        仍在（设计文档 §2.1）。
        """
        rows = DownloadService.list_completed_image_ids(page=1, page_size=limit)
        if not rows:
            return []

        ordered_ids = [image_id for image_id, _ in rows]
        with YandeDataRepository() as repo:
            records = {
                rec.id: rec
                for rec in repo.session.execute(
                    select(YandeData).where(YandeData.id.in_(ordered_ids))
                )
                .scalars()
                .all()
            }
            # 必须在 with 块**内**把需要的字段物化成普通值。
            # 直接把 ORM 实例存进 records 带出块外，__exit__ 里的 session.close()
            # 会把它们变成 detached instance；此后任何属性访问都要求重新加载，
            # 而 session 已关 → sqlalchemy.orm.exc.DetachedInstanceError。
            #
            # 注意与 expire_on_commit 无关：生产 _get_session_factory() 用的是
            # expire_on_commit=False（dao/database.py:125），属性并不会因为 commit
            # 而过期。真正的触发条件是「session 已关闭后访问未加载的属性」。
            # 即便这里所有列都是已加载的（deferred 未开启），把实例带出块外仍是
            # 危险写法——一旦有人给该列加 deferred(...)，或换成 lazy 关系，就会炸。
            meta = {
                rec.id: (
                    rec.tags or "",
                    rec.rating.display if rec.rating is not None else "",
                )
                for rec in records.values()
            }

        items: List[MyFavoritePreviewImage] = []
        for image_id in ordered_ids:
            row = meta.get(image_id)
            if row is None:
                # 任务表有记录但 yande_data 无对应元数据（历史脏数据），跳过而非报错
                continue
            tags, rating_display = row
            items.append(
                MyFavoritePreviewImage(
                    id=image_id,
                    preview_url=None,  # 前端 FolderTile 按 id 拼 /api/v1/gallery/cache/preview/{id}
                    tags=tags,
                    rating=rating_display,
                )
            )
        return items

    @staticmethod
    def delete_completed_records(days: Optional[int] = None) -> int:
        """清除「最近下载」已完成记录（只删任务日志，**不删**图片文件）。

        Args:
            days: None → 清空全部 completed 记录；
                  N（≥1）→ 只清除 ``completed_at < now - N days`` 的记录。

        Returns:
            删除的记录条数（0 表示无匹配）。

        安全红线：DAO 内部固定带 ``status == COMPLETED AND completed_at IS NOT NULL``，
        pending/downloading/paused/failed/cancelled 绝不会被删除。
        """
        from src.dao.download_task_dao import DownloadTaskDao

        with DownloadTaskDao() as dao:
            if days is None:
                return dao.delete_all_completed()
            cutoff = datetime.now() - timedelta(days=days)
            return dao.delete_completed_before(cutoff)
