"""我的最爱 ORM 模型（图片级标记中间表）"""
from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String

from src.common.constant import table_constant
from src.models.database.yande import Base


class MyFavorite(Base):
    """我的最爱 - 图片级标记（与 FavoriteFolder 互不污染）"""
    __tablename__ = table_constant.my_favorite

    id = Column(Integer, primary_key=True, autoincrement=True)
    image_id = Column(Integer, nullable=False, unique=True, comment="yande 图片 ID")
    created_at = Column(DateTime, default=datetime.now, comment="收藏时间")
    note = Column(String(255), nullable=True, comment="预留备注字段")