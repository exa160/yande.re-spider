"""下载任务数据访问层

设计原则：
- 写入仅由 TaskStore 在状态变更时触发，进度上报不落 DB
- 查询统一走 DB，避免内存与 DB 不一致
- 启动时通过 list_active() 恢复 pending/paused 任务
- recover_downloading_tasks() 处理崩溃残留
"""
from datetime import datetime
from typing import List, Optional, Tuple

from loguru import logger
from sqlalchemy import case, func, select, update

from src.common.constant import TaskStatus
from src.dao.database import BaseDAO
from src.models.database.yande import DownloadTask


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
