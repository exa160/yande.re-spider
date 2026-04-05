"""
收藏夹数据模型
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class FavoriteFolderBase(BaseModel):
    """收藏夹基础模型"""

    name: str = Field(..., min_length=1, max_length=50, description="收藏夹名称")
    tags: str = Field(default="", description="查询标签字符串，如 rating:s score:>100")
    color: str = Field(default="#409EFF", description="展示颜色，hex格式")
    icon: str = Field(default="folder", description="图标标识")
    sort_order: int = Field(default=0, description="排序权重")


class FavoriteFolderCreate(FavoriteFolderBase):
    """创建收藏夹请求模型"""

    pass


class FavoriteFolderUpdate(BaseModel):
    """更新收藏夹请求模型"""

    name: Optional[str] = Field(None, min_length=1, max_length=50)
    tags: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    sort_order: Optional[int] = None


class FavoriteFolder(FavoriteFolderBase):
    """收藏夹完整模型"""

    id: int
    local_count: int = 0
    online_count: int = 0
    last_refresh: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class FavoriteFolderWithCount(FavoriteFolder):
    """带图片数量的收藏夹模型"""

    preview_images: list = Field(default_factory=list, description="预览图片列表")


class ReorderRequest(BaseModel):
    """批量更新排序请求模型"""

    folder_ids: list[int] = Field(..., description="按新顺序排列的收藏夹ID列表")
