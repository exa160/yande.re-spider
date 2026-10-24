"""MyFavoriteDao - my_favorite 表的数据访问层"""
from typing import List, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.models.database.my_favorite import MyFavorite
from src.models.database.yande import YandeData


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
        """my_favorite 原始行数（含 yande_data 中已不存在的孤儿记录）。"""
        return session.query(MyFavorite).count()

    @staticmethod
    def count_with_images(session: Session) -> int:
        """可渲染的收藏数（INNER JOIN yande_data）。

        与 ``/my_favorites/images`` 的查询保持同一口径：图片记录缺失时，
        该收藏无法在瀑布流中展示，因此不应计入角标。本地 DB 被测试/备份
        还原后可能残留孤儿 my_favorite 行（此前出现 27 vs 11 的角标/列表差异）。
        """
        return (
            session.query(MyFavorite)
            .join(YandeData, YandeData.id == MyFavorite.image_id)
            .count()
        )

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