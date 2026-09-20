"""MyFavorites 响应模型"""
from typing import List, Optional

from pydantic import BaseModel, Field


class MyFavoriteCountResponse(BaseModel):
    """我的最爱总数响应"""
    count: int = Field(..., ge=0, description="我的最爱总数")


class MyFavoritesListItem(BaseModel):
    """列表项（含 image_id 和 created_at）"""
    id: int = Field(..., description="my_favorite 主键")
    image_id: int = Field(..., description="yande 图片 ID")
    created_at: str = Field(..., description="收藏时间 ISO 8601")


class MyFavoritesListResponse(BaseModel):
    """我的最爱分页列表响应"""
    total: int = Field(..., ge=0)
    page: int = Field(..., ge=1)
    page_size: int = Field(..., ge=1)
    data: List[MyFavoritesListItem] = Field(default_factory=list)


class MyFavoritePreviewImage(BaseModel):
    """预览图元数据（结构对齐 FavoriteFolderWithMinimalPreview.preview_images）"""
    id: int = Field(...)
    preview_url: Optional[str] = Field(default=None)
    tags: str = Field(default="")
    rating: str = Field(default="")


class MyFavoritePreviewResponse(BaseModel):
    """我的最爱预览响应"""
    images: List[MyFavoritePreviewImage] = Field(default_factory=list)
