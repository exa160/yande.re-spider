"""
收藏夹数据访问层
"""

from datetime import datetime
from typing import List, Optional

from sqlalchemy import Column, Integer, String, DateTime, Text
from sqlalchemy.orm import Session

from backend.dao.database import Base, get_db_engine


class FavoriteFolder(Base):
    """收藏夹数据库模型"""

    __tablename__ = "favorite_folders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False, comment="收藏夹名称")
    tags = Column(Text, default="", comment="查询标签字符串")
    color = Column(String(10), default="#409EFF", comment="展示颜色")
    icon = Column(String(32), default="folder", comment="图标标识")
    sort_order = Column(Integer, default=0, comment="排序权重")
    local_count = Column(Integer, default=0, comment="本地图片数量")
    online_count = Column(Integer, default=0, comment="在线图片数量(缓存)")
    last_refresh = Column(DateTime, nullable=True, comment="最后刷新时间")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    updated_at = Column(
        DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间"
    )


class FavoriteDao:
    """收藏夹数据访问对象"""

    def __init__(self):
        self.engine = get_db_engine()

    def _get_session(self) -> Session:
        from sqlalchemy.orm import Session

        return Session(bind=self.engine)

    def create(
        self,
        name: str,
        tags: str = "",
        color: str = "#409EFF",
        icon: str = "folder",
        sort_order: int = 0,
    ) -> FavoriteFolder:
        """创建收藏夹"""
        session = self._get_session()
        try:
            folder = FavoriteFolder(
                name=name, tags=tags, color=color, icon=icon, sort_order=sort_order
            )
            session.add(folder)
            session.commit()
            session.refresh(folder)
            return folder
        finally:
            session.close()

    def get_by_id(self, folder_id: int) -> Optional[FavoriteFolder]:
        """根据ID获取收藏夹"""
        session = self._get_session()
        try:
            return (
                session.query(FavoriteFolder)
                .filter(FavoriteFolder.id == folder_id)
                .first()
            )
        finally:
            session.close()

    def get_all(self) -> List[FavoriteFolder]:
        """获取所有收藏夹，按sort_order排序"""
        session = self._get_session()
        try:
            return (
                session.query(FavoriteFolder)
                .order_by(FavoriteFolder.sort_order.asc())
                .all()
            )
        finally:
            session.close()

    def update(self, folder_id: int, **kwargs) -> Optional[FavoriteFolder]:
        """更新收藏夹"""
        session = self._get_session()
        try:
            folder = (
                session.query(FavoriteFolder)
                .filter(FavoriteFolder.id == folder_id)
                .first()
            )
            if not folder:
                return None

            for key, value in kwargs.items():
                if value is not None and hasattr(folder, key):
                    setattr(folder, key, value)

            folder.updated_at = datetime.now()
            session.commit()
            session.refresh(folder)
            return folder
        finally:
            session.close()

    def delete(self, folder_id: int) -> bool:
        """删除收藏夹"""
        session = self._get_session()
        try:
            folder = (
                session.query(FavoriteFolder)
                .filter(FavoriteFolder.id == folder_id)
                .first()
            )
            if not folder:
                return False
            session.delete(folder)
            session.commit()
            return True
        finally:
            session.close()

    def reorder(self, folder_ids: List[int]) -> bool:
        """批量更新排序"""
        session = self._get_session()
        try:
            for order, folder_id in enumerate(folder_ids):
                folder = (
                    session.query(FavoriteFolder)
                    .filter(FavoriteFolder.id == folder_id)
                    .first()
                )
                if folder:
                    folder.sort_order = order
                    folder.updated_at = datetime.now()
            session.commit()
            return True
        except Exception:
            session.rollback()
            return False
        finally:
            session.close()

    def count(self) -> int:
        """获取收藏夹总数"""
        session = self._get_session()
        try:
            return session.query(FavoriteFolder).count()
        finally:
            session.close()


# 全局实例
favorite_dao = FavoriteDao()
