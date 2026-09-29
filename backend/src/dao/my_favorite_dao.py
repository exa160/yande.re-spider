"""MyFavoriteDao - my_favorite 表的数据访问层"""
from typing import List, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.models.database.my_favorite import MyFavorite


class MyFavoriteDao:
    """我的最爱 DAO。UNIQUE(image_id) 保证幂等。"""

    @staticmethod
    def add(session: Session, image_id: int, note: Optional[str] = None) -> None:
        """加入我的最爱。幂等（UNIQUE image_id 兜底）。

        使用 SAVEPOINT (begin_nested) 而非 session.rollback()——后者会把
        当前事务里之前成功 add() 的其它记录也一起回滚，破坏批量加入场景。
        """
        record = MyFavorite(image_id=image_id, note=note)
        try:
            with session.begin_nested():
                session.add(record)
                session.flush()
        except IntegrityError:
            pass  # SAVEPOINT 自动回滚；外层事务不受影响

    @staticmethod
    def remove(session: Session, image_id: int) -> None:
        """取消我的最爱。幂等（不存在不报错）。"""
        session.query(MyFavorite).filter(MyFavorite.image_id == image_id).delete()
        session.flush()

    @staticmethod
    def list_paginated(session: Session, page: int = 1, page_size: int = 20) -> List[MyFavorite]:
        """分页列出（按 created_at DESC）。"""
        offset = (page - 1) * page_size
        return (
            session.query(MyFavorite)
            .order_by(MyFavorite.created_at.desc())
            .offset(offset)
            .limit(page_size)
            .all()
        )

    @staticmethod
    def count(session: Session) -> int:
        """总数。"""
        return session.query(MyFavorite).count()

    @staticmethod
    def get_preview(session: Session, limit: int = 20) -> List[dict]:
        """我的最爱预览图元数据（JOIN yande_data 按 created_at DESC）。

        返回字典列表，结构对齐 FavoriteFolderWithMinimalPreview.preview_images：
        [{"id": int, "preview_url": str, "tags": str, "rating": str}, ...]
        """
        from src.models.database.yande import YandeData
        records = (
            session.query(MyFavorite, YandeData)
            .join(YandeData, YandeData.id == MyFavorite.image_id)
            .order_by(MyFavorite.created_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id": yande.id,
                "preview_url": yande.preview_url,
                "tags": yande.tags,
                "rating": yande.rating,
            }
            for _, yande in records
        ]