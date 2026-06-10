from datetime import datetime
from typing import List, Optional, Type

from src.dao.database import BaseDAO
from src.models.database.yande import FavoriteFolder


class FavoriteDao(BaseDAO):

    def create(
        self,
        name: str,
        tags: str = "",
        color: str = "#409EFF",
        icon: str = "folder",
        sort_order: int = 0,
        schedule_enabled: bool = False,
        schedule_cron: str = "",
        schedule_mode: str = "last_id",
        schedule_max_images: Optional[int] = None,
    ) -> FavoriteFolder:
        folder = FavoriteFolder(
            name=name,
            tags=tags,
            color=color,
            icon=icon,
            sort_order=sort_order,
            schedule_enabled=schedule_enabled,
            schedule_cron=schedule_cron,
            schedule_mode=schedule_mode,
            schedule_max_images=schedule_max_images,
        )
        self.session.add(folder)
        self.session.flush()
        return folder

    def get_by_id(self, folder_id: int) -> Optional[FavoriteFolder]:
        return self.session.query(FavoriteFolder).filter(FavoriteFolder.id == folder_id).first()

    def get_all(self) -> list[Type[FavoriteFolder]]:
        return (
            self.session.query(FavoriteFolder)
            .order_by(FavoriteFolder.sort_order.asc())
            .all()
        )

    def update(self, folder_id: int, **kwargs) -> Optional[FavoriteFolder]:
        folder = self.session.query(FavoriteFolder).filter(FavoriteFolder.id == folder_id).first()
        if not folder:
            return None

        for key, value in kwargs.items():
            if hasattr(folder, key):
                setattr(folder, key, value)

        folder.updated_at = datetime.now()
        self.session.flush()
        return folder

    def delete(self, folder_id: int) -> bool:
        folder = self.session.query(FavoriteFolder).filter(FavoriteFolder.id == folder_id).first()
        if not folder:
            return False
        self.session.delete(folder)
        return True

    def get_scheduled_folders(self) -> List[FavoriteFolder]:
        """取出所有启用了调度的收藏夹。供 lifespan 和定时任务使用。"""
        return (
            self.session.query(FavoriteFolder)
            .filter(FavoriteFolder.schedule_enabled == True)  # noqa: E712
            .all()
        )

    def reorder(self, folder_ids: List[int]) -> bool:
        for order, folder_id in enumerate(folder_ids):
            folder = self.session.query(FavoriteFolder).filter(FavoriteFolder.id == folder_id).first()
            if folder:
                folder.sort_order = order
                folder.updated_at = datetime.now()
        return True

    def count(self) -> int:
        return self.session.query(FavoriteFolder).count()


favorite_dao = FavoriteDao()