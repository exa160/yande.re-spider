from typing import List, Optional, Tuple

from loguru import logger
from sqlalchemy import select, func
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from src.common import config
from src.common.constant import TaskStatus
from src.dao.database import BaseDAO
from src.models.database.yande import DownloadTaskModel


class DownloadTaskRepository(BaseDAO):

    def create(self, task_data: dict) -> DownloadTaskModel:
        record = DownloadTaskModel(**task_data)
        self.session.add(record)
        self.session.flush()
        return record

    def upsert(self, task_data: dict) -> None:
        use_mariadb = config.database.enable and config.database.host
        if use_mariadb:
            stmt = mysql_insert(DownloadTaskModel).values(task_data)
            update_cols = {
                k: stmt.inserted[k]
                for k in task_data.keys()
                if k != "task_id"
            }
            stmt = stmt.on_duplicate_key_update(**update_cols)
        else:
            stmt = sqlite_insert(DownloadTaskModel).values(task_data)
            stmt = stmt.on_conflict_do_update(
                index_elements=[DownloadTaskModel.task_id],
                set_={
                    k: stmt.excluded[k]
                    for k in task_data.keys()
                    if k != "task_id"
                },
            )
        self.session.execute(stmt)

    def get_by_id(self, task_id: str) -> Optional[DownloadTaskModel]:
        stmt = select(DownloadTaskModel).filter_by(task_id=task_id)
        return self.session.execute(stmt).scalar_one_or_none()

    def get_tasks(
        self,
        status: Optional[TaskStatus] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[DownloadTaskModel], int]:
        stmt = select(DownloadTaskModel)
        count_stmt = select(func.count()).select_from(DownloadTaskModel)

        if status:
            stmt = stmt.filter(DownloadTaskModel.status == status)
            count_stmt = count_stmt.filter(DownloadTaskModel.status == status)

        total = self.session.execute(count_stmt).scalar() or 0
        offset = (page - 1) * page_size
        results = self.session.execute(
            stmt.order_by(DownloadTaskModel.created_at.desc())
            .offset(offset)
            .limit(page_size)
        ).scalars().all()

        return results, total

    def update(self, task_id: str, **updates) -> bool:
        try:
            record = self.get_by_id(task_id)
            if record:
                for key, value in updates.items():
                    if hasattr(record, key):
                        setattr(record, key, value)
                return True
            return False
        except Exception as e:
            logger.warning(f"Update download task error: {e}")
            return False

    def delete(self, task_id: str) -> bool:
        record = self.get_by_id(task_id)
        if record:
            self.session.delete(record)
            return True
        return False

    def load_pending_tasks(self) -> List[DownloadTaskModel]:
        stmt = select(DownloadTaskModel).filter(
            DownloadTaskModel.status.in_([
                TaskStatus.PENDING,
                TaskStatus.DOWNLOADING,
                TaskStatus.PAUSED,
            ])
        )
        return self.session.execute(stmt).scalars().all()
