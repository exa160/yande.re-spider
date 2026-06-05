
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from src.models.response.base_response import BaseResponse


class FavoriteFolderBase(BaseModel):
    """收藏夹基础模型"""

    name: str = Field(..., min_length=1, max_length=50, description="收藏夹名称")
    tags: str = Field(default="", description="查询标签字符串，如 rating:s score:>100")
    color: str = Field(default="#409EFF", description="展示颜色，hex格式")
    icon: str = Field(default="folder", description="图标标识")
    sort_order: int = Field(default=0, description="排序权重")


class FavoriteFolder(FavoriteFolderBase):
    """收藏夹完整模型"""

    id: int
    local_count: int = 0
    online_count: int = 0
    last_refresh: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    schedule_enabled: bool = False
    schedule_cron: str = ""
    schedule_mode: str = "last_id"
    schedule_max_images: Optional[int] = None
    last_scheduled_at: Optional[datetime] = None
    last_schedule_status: Optional[str] = None
    last_schedule_stats: Optional[dict] = None

    model_config = ConfigDict(from_attributes=True)


class FavoriteFolderWithPreview(FavoriteFolder):
    """带图片预览的收藏夹模型"""

    preview_images: list = Field(default_factory=list, description="预览图片列表")


class FavoriteFolderResponse(BaseResponse[FavoriteFolder]):
    """
    查询响应 - 收藏夹详情
    """
    ...


class FavoriteFoldersResponse(BaseResponse[list[FavoriteFolder]]):
    """
    查询响应 - 收藏夹详情列表
    """
    ...


class FavoriteFolderWithPreviewResponse(BaseResponse[FavoriteFolderWithPreview]):
    """
    查询响应 - 带图片预览的收藏夹详情
    """
    ...


class FavoriteFoldersWithPreviewResponse(BaseResponse[list[FavoriteFolderWithPreview]]):
    """
    查询响应 - 带图片预览的收藏夹详情列表
    """
    ...


class FavoriteFoldersResponse(BaseResponse[list[FavoriteFolder]]):
    """
    查询响应 - 收藏夹详情列表
    """
    ...


class FavoriteFolderWithPreviewResponse(BaseResponse[FavoriteFolderWithPreview]):
    """
    查询响应 - 带图片预览的收藏夹详情
    """
    ...


class FavoriteFoldersWithPreviewResponse(BaseResponse[list[FavoriteFolderWithPreview]]):
    """
    查询响应 - 带图片预览的收藏夹详情
    """
    ...