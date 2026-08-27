from datetime import datetime
from typing import List, Optional, Type

from sqlalchemy import func, or_

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

    def list_paginated(self, page: int, page_size: int) -> tuple[list[FavoriteFolder], int]:
        """分页获取收藏夹，按 sort_order 升序。

        Returns:
            (items, total): items 为当前页的 FavoriteFolder 列表，total 为总数
        """
        total = (
            self.session.query(func.count(FavoriteFolder.id))
            .scalar() or 0
        )
        offset = (page - 1) * page_size
        items = (
            self.session.query(FavoriteFolder)
            .order_by(FavoriteFolder.sort_order.asc())
            .offset(offset)
            .limit(page_size)
            .all()
        )
        return items, total

    def search_paginated(
        self, page: int, page_size: int, keyword: str
    ) -> tuple[list[FavoriteFolder], int]:
        """分页搜索收藏夹，按 name / tags 模糊匹配（不区分大小写）。

        Args:
            keyword: 搜索关键字，空格分隔的 token 按 OR 关系匹配（任一 token 命中 name 或 tags 即可）

        Returns:
            (items, total): items 为当前页，total 为匹配总数（供前端 has_more 计算）
        """
        kw = (keyword or "").strip()
        if not kw:
            return self.list_paginated(page=page, page_size=page_size)

        tokens = [t for t in kw.split() if t]
        if not tokens:
            return self.list_paginated(page=page, page_size=page_size)

        # 任一 token 命中 name 或 tags 即视为匹配（多 token 是 OR，不是 AND）
        # 用 SQL LIKE 双侧通配实现 'contains' 语义
        filters = []
        for t in tokens:
            pat = f"%{t}%"
            filters.append(
                or_(
                    FavoriteFolder.name.ilike(pat),
                    FavoriteFolder.tags.ilike(pat),
                )
            )
        cond = or_(*filters)

        total = (
            self.session.query(func.count(FavoriteFolder.id)).filter(cond).scalar() or 0
        )
        offset = (page - 1) * page_size
        items = (
            self.session.query(FavoriteFolder)
            .filter(cond)
            .order_by(FavoriteFolder.sort_order.asc())
            .offset(offset)
            .limit(page_size)
            .all()
        )
        return items, total

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

    def reset_last_synced_id(self, folder_id: int, new_value: Optional[int] = None) -> Optional[FavoriteFolder]:
        """重置 last_synced_id，new_value=None 时清空（下次回到首次行为）。"""
        return self.update(folder_id, last_synced_id=new_value)

    def count(self) -> int:
        return self.session.query(FavoriteFolder).count()


favorite_dao = FavoriteDao()