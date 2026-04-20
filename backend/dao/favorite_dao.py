"""
收藏夹数据访问层

使用新的 DatabaseManager 进行会话管理和事务控制。
"""

from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from backend.src.model.database import DatabaseManager, get_session_factory
from backend.src.model.database.models import FavoriteFolder


class FavoriteDao:
    """收藏夹数据访问对象"""

    def __init__(self):
        self._session = None

    @property
    def session(self) -> Session:
        if self._session is None:
            self._session = get_session_factory()()
        return self._session

    def _close_session(self):
        if self._session:
            self._session.close()
            self._session = None

    def create(
        self,
        name: str,
        tags: str = "",
        color: str = "#409EFF",
        icon: str = "folder",
        sort_order: int = 0,
    ) -> FavoriteFolder:
        """创建收藏夹"""
        try:
            folder = FavoriteFolder(
                name=name, tags=tags, color=color, icon=icon, sort_order=sort_order
            )
            self.session.add(folder)
            self.session.commit()
            self.session.refresh(folder)
            return folder
        except Exception as e:
            self.session.rollback()
            raise
        finally:
            self._close_session()

    def get_by_id(self, folder_id: int) -> Optional[FavoriteFolder]:
        """根据ID获取收藏夹"""
        try:
            return (
                self.session.query(FavoriteFolder)
                .filter(FavoriteFolder.id == folder_id)
                .first()
            )
        finally:
            self._close_session()

    def get_all(self) -> List[FavoriteFolder]:
        """获取所有收藏夹，按sort_order排序"""
        try:
            return (
                self.session.query(FavoriteFolder)
                .order_by(FavoriteFolder.sort_order.asc())
                .all()
            )
        finally:
            self._close_session()

    def update(self, folder_id: int, **kwargs) -> Optional[FavoriteFolder]:
        """更新收藏夹"""
        try:
            folder = (
                self.session.query(FavoriteFolder)
                .filter(FavoriteFolder.id == folder_id)
                .first()
            )
            if not folder:
                return None

            for key, value in kwargs.items():
                if value is not None and hasattr(folder, key):
                    setattr(folder, key, value)

            folder.updated_at = datetime.now()
            self.session.commit()
            self.session.refresh(folder)
            return folder
        except Exception:
            self.session.rollback()
            raise
        finally:
            self._close_session()

    def delete(self, folder_id: int) -> bool:
        """删除收藏夹"""
        try:
            folder = (
                self.session.query(FavoriteFolder)
                .filter(FavoriteFolder.id == folder_id)
                .first()
            )
            if not folder:
                return False
            self.session.delete(folder)
            self.session.commit()
            return True
        except Exception:
            self.session.rollback()
            return False
        finally:
            self._close_session()

    def reorder(self, folder_ids: List[int]) -> bool:
        """批量更新排序"""
        try:
            for order, folder_id in enumerate(folder_ids):
                folder = (
                    self.session.query(FavoriteFolder)
                    .filter(FavoriteFolder.id == folder_id)
                    .first()
                )
                if folder:
                    folder.sort_order = order
                    folder.updated_at = datetime.now()
            self.session.commit()
            return True
        except Exception:
            self.session.rollback()
            return False
        finally:
            self._close_session()

    def count(self) -> int:
        """获取收藏夹总数"""
        try:
            return self.session.query(FavoriteFolder).count()
        finally:
            self._close_session()


# 全局实例
favorite_dao = FavoriteDao()
