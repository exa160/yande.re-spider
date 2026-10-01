"""下载任务数据访问层

设计原则：
- 写入仅由 TaskStore 在状态变更时触发，进度上报不落 DB
- 查询统一走 DB，避免内存与 DB 不一致
- 启动时通过 list_active() 恢复 pending/paused 任务
- recover_downloading_tasks() 处理崩溃残留
"""
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from loguru import logger
from sqlalchemy import case, delete, func, select, update

from src.common.constant import TaskStatus
from src.dao.database import BaseDAO
from src.models.database.yande import DownloadTask

# 活跃状态：任务还在队列里（前端据此显示「下载中」）
ACTIVE_STATUSES = (TaskStatus.PENDING, TaskStatus.DOWNLOADING, TaskStatus.PAUSED)
# 终态：任务已结束（前端据此收敛「下载中 → 已下载 / 复位」）
FINISHED_STATUSES = (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED)


class DownloadTaskDao(BaseDAO):
    """下载任务 DAO

    字段说明：
    - task_id: UUID v4 字符串（主键）
    - image_id: yande 图片 ID（冗余存储，不外键）
    - status: 任务状态枚举
    """

    def create(
        self,
        task_id: str,
        image_id: int,
        file_name: str,
        file_size: Optional[int] = None,
    ) -> DownloadTask:
        """创建任务记录（DB 写入）"""
        record = DownloadTask(
            task_id=task_id,
            image_id=image_id,
            file_name=file_name,
            file_size=file_size,
            status=TaskStatus.PENDING,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        self.session.add(record)
        self.session.flush()
        return record

    def get_by_id(self, task_id: str) -> Optional[DownloadTask]:
        """根据 task_id 查询"""
        return (
            self.session.query(DownloadTask)
            .filter_by(task_id=task_id)
            .first()
        )

    def list_active(self) -> List[DownloadTask]:
        """拉取活跃任务（pending/paused）供启动恢复"""
        return (
            self.session.query(DownloadTask)
            .filter(
                DownloadTask.status.in_([
                    TaskStatus.PENDING,
                    TaskStatus.PAUSED,
                ])
            )
            .all()
        )

    def recover_downloading_tasks(self) -> int:
        """崩溃恢复：把残留的 downloading 任务改为 pending"""
        stmt = (
            update(DownloadTask)
            .where(DownloadTask.status == TaskStatus.DOWNLOADING)
            .values(
                status=TaskStatus.PENDING,
                error_message="进程崩溃后恢复",
                updated_at=datetime.now(),
            )
        )
        result = self.session.execute(stmt)
        count = result.rowcount or 0
        if count:
            logger.warning(f"DownloadTaskDao: 崩溃恢复 {count} 个残留 downloading → pending")
        return count

    def update(self, task_id: str, **kwargs) -> Optional[DownloadTask]:
        """更新任务字段（仅状态变更时调用）"""
        record = self.get_by_id(task_id)
        if not record:
            return None
        for key, value in kwargs.items():
            if value is not None and hasattr(record, key):
                setattr(record, key, value)
        record.updated_at = datetime.now()
        self.session.flush()
        return record

    def delete(self, task_id: str) -> bool:
        """删除任务记录"""
        record = self.get_by_id(task_id)
        if not record:
            return False
        self.session.delete(record)
        return True

    def query(
        self,
        status: Optional[TaskStatus] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[dict], int]:
        """分页查询，统一返回 dict 列表（与 TaskStore.get_tasks API 一致）"""
        stmt = select(DownloadTask)
        count_stmt = select(func.count()).select_from(DownloadTask)
        if status:
            stmt = stmt.filter(DownloadTask.status == status)
            count_stmt = count_stmt.filter(DownloadTask.status == status)

        total = self.session.execute(count_stmt).scalar() or 0
        records = (
            self.session.execute(
                stmt.order_by(DownloadTask.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            .scalars()
            .all()
        )
        return [self._to_dict(r) for r in records], total

    def count_by_status(self) -> dict:
        """按 status 统计任务数（单 SQL GROUP BY），缺失状态为 0"""
        rows = self.session.query(
            DownloadTask.status,
            func.count(DownloadTask.task_id)
        ).group_by(DownloadTask.status).all()

        result = {s.value: 0 for s in TaskStatus}
        for status_val, count in rows:
            key = status_val.value if hasattr(status_val, "value") else status_val
            result[key] = count
        return result

    def active_states_by_image(self) -> Dict[int, DownloadTask]:
        """活跃任务（pending/downloading/paused）按 image_id 聚合。

        同一张图片可能存在多条任务（重复点下载），按 created_at DESC 排序后
        「首次出现即最新」，同名 image_id 只保留最新一条。

        Returns:
            {image_id: DownloadTask}；无活跃任务返回空 dict
        """
        rows = (
            self.session.query(DownloadTask)
            .filter(DownloadTask.status.in_(ACTIVE_STATUSES))
            .order_by(DownloadTask.image_id.asc(), DownloadTask.created_at.desc())
            .all()
        )
        result: Dict[int, DownloadTask] = {}
        for row in rows:
            result.setdefault(row.image_id, row)
        return result

    def finished_states_by_image(self, since: datetime) -> Dict[int, str]:
        """窗口期内进入终态的任务按 image_id 聚合，返回 {image_id: status}。

        与 active_states_by_image 同理，同一 image_id 只保留 updated_at 最新的一条。
        窗口（since）由调用方给出，用于让前端在「任务刚结束」这一小段时间内
        仍能观察到 completed/failed，从而把「下载中」标识收敛掉。

        Args:
            since: 终态时间的下界（updated_at >= since）

        Returns:
            {image_id: 'completed' | 'failed' | 'cancelled'}
        """
        rows = (
            self.session.query(DownloadTask)
            .filter(
                DownloadTask.status.in_(FINISHED_STATUSES),
                DownloadTask.updated_at >= since,
            )
            .order_by(DownloadTask.image_id.asc(), DownloadTask.updated_at.desc())
            .all()
        )
        result: Dict[int, str] = {}
        for row in rows:
            status = row.status.value if hasattr(row.status, "value") else row.status
            result.setdefault(row.image_id, status)
        return result

    def query_tasks(
        self,
        status_list: Optional[List[TaskStatus]] = None,
        sort_by: str = "created_at",
        order: str = "desc",
        page: int = 1,
        page_size: int = 20,
        download_first: bool = False,
    ) -> Tuple[List[dict], int]:
        """分页查询任务（多状态过滤 + 排序 + 分页）。

        Args:
            status_list: 状态过滤列表；None/[] 表示所有
            sort_by: 排序字段（image_id/created_at/updated_at/completed_at/progress）
            order: 'asc' | 'desc'
            page: 页码
            page_size: 每页数量
            download_first: 是否将 status='downloading' 的任务排在最前（用于 active tab
                默认排序：先看正在下载的任务）。第二排序键仍为 sort_by + order。
        """
        allowed_sort = {"image_id", "created_at", "updated_at", "completed_at", "progress"}
        if sort_by not in allowed_sort:
            raise ValueError(f"Invalid sort_by: {sort_by}. Must be one of {allowed_sort}")
        if order not in ("asc", "desc"):
            raise ValueError(f"Invalid order: {order}. Must be 'asc' or 'desc'")

        stmt = select(DownloadTask)
        count_stmt = select(func.count()).select_from(DownloadTask)

        if status_list:
            status_values = [s.value if hasattr(s, "value") else s for s in status_list]
            stmt = stmt.filter(DownloadTask.status.in_(status_values))
            count_stmt = count_stmt.filter(DownloadTask.status.in_(status_values))

        total = self.session.execute(count_stmt).scalar() or 0

        order_clauses = []
        if download_first:
            # CASE WHEN status='downloading' THEN 0 ELSE 1 END
            # 把 downloading 任务排到 group 0，其他排到 group 1
            # 组内仍按 sort_by + order 排
            order_clauses.append(
                case(
                    (DownloadTask.status == TaskStatus.DOWNLOADING.value, 0),
                    else_=1,
                ).asc()
            )
        sort_col = getattr(DownloadTask, sort_by)
        order_clauses.append(sort_col.asc() if order == "asc" else sort_col.desc())

        stmt = stmt.order_by(*order_clauses)
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        records = self.session.execute(stmt).scalars().all()

        return [self._to_dict(r) for r in records], total

    # ============================================================
    # 「最近下载」功能（设计文档 2026-09-21-recent-downloads-design.md §3.1）
    #
    # 数据源说明：yande_data 表没有「本地下载时间」列（created_at/updated_at 是
    # yande.re 图源的上传/更新时间，与本地下载无关），因此复用 download_task 的
    # completed_at 作为「最近下载」的唯一时间依据，且本期不改表结构。
    #
    # 下面 4 个方法共用一组**缺一不可**的筛选条件：
    #   1. status == COMPLETED —— 排除 pending/downloading/paused/failed/cancelled，
    #      避免未完成的队列在「最近下载」里露头，也保证清除操作绝不误删在途任务。
    #   2. completed_at IS NOT NULL —— download_queue 在「文件已存在、跳过下载」分支
    #      不会写 completed_at，这类记录 completed_at 为 NULL，时间未知，必须排除
    #      （否则按 MAX(completed_at) 排序会沉底甚至让 total 口径虚高）。
    #   3. GROUP BY image_id + MAX(completed_at) —— 同一张图重复下载会产生多条
    #      completed 记录，去重后每张图只出现一次，取最新完成时间作为排序键，
    #      同时让 COUNT(DISTINCT image_id) 与列表口径严格一致。
    # ============================================================

    def list_completed_image_ids(
        self, page: int = 1, page_size: int = 20
    ) -> List[Tuple[int, datetime]]:
        """分页返回已完成任务的 image_id + MAX(completed_at)，按 MAX(completed_at) DESC。

        筛选条件（缺一不可，理由见上方区块注释）：
        status == COMPLETED AND completed_at IS NOT NULL，
        并以 GROUP BY image_id 去重（重复下载只保留一条，取最新完成时间）。

        Args:
            page: 页码，从 1 开始
            page_size: 每页数量

        Returns:
            [(image_id, latest_completed_at), ...]，按最新完成时间倒序。
            无匹配返回空列表。
        """
        stmt = (
            select(
                DownloadTask.image_id,
                func.max(DownloadTask.completed_at).label("latest_completed_at"),
            )
            .where(
                DownloadTask.status == TaskStatus.COMPLETED,
                DownloadTask.completed_at.isnot(None),
            )
            .group_by(DownloadTask.image_id)
            # 第二排序键 image_id：纯时间序在同秒完成的任务之间没有确定顺序，
            # 翻页时同一批数据可能给出不同的分页切分（重复/漏项）。加确定性 tiebreaker
            # 消除这一点。翻页期间有新任务完成导致的 offset 位移是 offset 分页的
            # 固有性质，彻底解决需改游标分页，本期不做。
            .order_by(
                func.max(DownloadTask.completed_at).desc(),
                DownloadTask.image_id.desc(),
            )
            .offset((max(page, 1) - 1) * page_size)
            .limit(page_size)
        )
        rows = self.session.execute(stmt).all()
        return [(row[0], row[1]) for row in rows]

    def count_completed_distinct_images(self) -> int:
        """COUNT(DISTINCT image_id)，口径与 list_completed_image_ids 对齐。

        用 COUNT(DISTINCT image_id) 而非 COUNT(*)：重复下载会让 COUNT(*) 虚高，
        角标数字与实际图片数对不上。筛选条件同样必须带上
        status == COMPLETED AND completed_at IS NOT NULL。
        """
        stmt = select(func.count(func.distinct(DownloadTask.image_id))).where(
            DownloadTask.status == TaskStatus.COMPLETED,
            DownloadTask.completed_at.isnot(None),
        )
        return self.session.execute(stmt).scalar() or 0

    def delete_completed_before(self, cutoff: datetime) -> int:
        """删除 completed_at < cutoff 且 status=COMPLETED 的记录。返回删除条数。

        安全红线：只删 status == COMPLETED 的记录。pending/downloading/paused/
        failed/cancelled 一律保留（下载管理页仍能看到历史与在途任务）。
        completed_at IS NOT NULL 显式带上，与列表口径对齐。

        Args:
            cutoff: 时间下界（只删严格早于它的记录），由 service 层按 days 换算
        """
        stmt = delete(DownloadTask).where(
            DownloadTask.status == TaskStatus.COMPLETED,
            DownloadTask.completed_at.isnot(None),
            DownloadTask.completed_at < cutoff,
        )
        result = self.session.execute(stmt)
        count = result.rowcount or 0
        if count:
            logger.info(f"DownloadTaskDao: 清除 {count} 条 {cutoff} 前的 completed 记录")
        return count

    def delete_all_completed(self) -> int:
        """删除全部 status=COMPLETED 且 completed_at 非空的记录。返回删除条数。

        安全红线（同 delete_completed_before）：绝不删除 pending/downloading/
        paused/failed/cancelled 记录 —— 用户误点「清空」时队列中的任务必须存活。

        已知取舍：与下载管理页的「已完成」历史共用同一批数据，清空后该页历史
        也会一并消失（设计文档 §2.1 已确认接受）；本方法只删任务日志，
        **不删**磁盘上的图片文件，也不改 yande_data.down_flag。
        """
        stmt = delete(DownloadTask).where(
            DownloadTask.status == TaskStatus.COMPLETED,
            DownloadTask.completed_at.isnot(None),
        )
        result = self.session.execute(stmt)
        count = result.rowcount or 0
        if count:
            logger.info(f"DownloadTaskDao: 清空 {count} 条 completed 下载记录")
        return count

    @staticmethod
    def _to_dict(record: DownloadTask) -> dict:
        """ORM → API dict（与 TaskStore.DownloadTask.model_dump 字段对齐）"""
        return {
            "task_id": record.task_id,
            "image_id": record.image_id,
            "file_name": record.file_name,
            "file_size": record.file_size,
            "downloaded_size": record.downloaded_size or 0,
            "progress": record.progress or 0.0,
            "speed": record.speed or 0.0,
            "status": (
                record.status.value
                if hasattr(record.status, "value")
                else record.status
            ),
            "error_message": record.error_message,
            "started_at": (
                record.started_at.isoformat() if record.started_at else None
            ),
            "completed_at": (
                record.completed_at.isoformat() if record.completed_at else None
            ),
            "created_at": (
                record.created_at.isoformat() if record.created_at else None
            ),
        }


download_task_dao = DownloadTaskDao()
