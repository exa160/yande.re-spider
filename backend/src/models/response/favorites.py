
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
    last_synced_id: Optional[int] = Field(default=None, description="上次调度实际同步到的最大图片ID，NULL=未初始化")

    model_config = ConfigDict(from_attributes=True)


class FavoriteFolderWithPreview(FavoriteFolder):
    """带图片预览的收藏夹模型"""

    preview_images: list = Field(default_factory=list, description="预览图片列表")


# ============================================
# Data sub-models (嵌套用，Pydantic 自动校验)
# ============================================

class FolderCountData(BaseModel):
    """收藏夹数量更新（在线/本地）的 data 模型"""
    count: int = Field(..., description="更新后的数量值")


class PreviewImage(BaseModel):
    """预览图片（接受 YandeData ORM 对象）"""
    id: int
    tags: Optional[str] = None
    file_url: Optional[str] = None
    preview_url: Optional[str] = None
    sample_url: Optional[str] = None
    jpeg_url: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    file_ext: Optional[str] = None
    file_size: Optional[int] = None
    down_flag: Optional[bool] = None
    rating: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class PreviewData(BaseModel):
    """收藏夹预览结果的 data 模型"""
    total: int = Field(..., description="匹配的总图片数")
    preview_images: list[PreviewImage] = Field(default_factory=list, description="预览图片列表（已下载）")

    model_config = ConfigDict(from_attributes=True)


class ScheduleTriggerStatsData(BaseModel):
    """调度任务运行统计的 data 模型"""
    status: str = Field(
        default="completed",
        description="本次响应状态：completed=同步执行已返回完整 stats；queued=已加入后台任务立即返回",
    )
    new_images: int = Field(default=0, description="本次发现的新图数")
    enqueued: int = Field(default=0, description="实际入下载队列的图数")
    skipped: int = Field(default=0, description="跳过入队的图数")
    pages_fetched: int = Field(default=0, description="抓取的 yande.re API 页数")
    duration_sec: float = Field(default=0.0, description="整个调度耗时（秒）")
    errors: list = Field(default_factory=list, description="错误信息列表")

    model_config = ConfigDict(from_attributes=True)


class FolderScheduleStatusData(BaseModel):
    """收藏夹调度状态的 data 模型（8 字段，省去前端重复解构）"""
    schedule_enabled: bool
    schedule_cron: str
    schedule_mode: str
    schedule_max_images: Optional[int]
    last_scheduled_at: Optional[datetime]
    last_schedule_status: Optional[str]
    last_schedule_stats: Optional[dict]
    last_synced_id: Optional[int] = Field(default=None, description="上次调度实际同步到的最大图片ID")

    model_config = ConfigDict(from_attributes=True)


# ============================================
# Response Models（继承 BaseResponse，data 强类型）
# ============================================

class FavoriteFolderResponse(BaseResponse[FavoriteFolder]):
    """查询响应 - 收藏夹详情（单个）"""
    ...


class FavoriteFoldersResponse(BaseResponse[list[FavoriteFolder]]):
    """查询响应 - 收藏夹详情列表"""
    ...


class FavoriteFolderWithPreviewResponse(BaseResponse[FavoriteFolderWithPreview]):
    """查询响应 - 带图片预览的收藏夹详情（单个）"""
    ...


class FavoriteFoldersWithPreviewResponse(BaseResponse[list[FavoriteFolderWithPreview]]):
    """查询响应 - 带图片预览的收藏夹详情列表"""
    ...


class FavoriteFolderUpdateResponse(BaseResponse[FavoriteFolder]):
    """更新响应 - 返回更新后的收藏夹"""
    ...


class FavoriteFolderPreviewResponse(BaseResponse[PreviewData]):
    """预览响应 - 返回 total + preview_images"""
    ...


class FavoriteFolderRefreshResponse(BaseResponse[FavoriteFolder]):
    """刷新响应 - 返回刷新后的收藏夹"""
    ...


class FolderCountResponse(BaseResponse[FolderCountData]):
    """数量更新响应 - online-count / refresh-online / local-count 共用"""
    ...


class ScheduleTriggerResponse(BaseResponse[ScheduleTriggerStatsData]):
    """调度触发响应 - 返回本次运行统计"""
    ...


class FolderScheduleStatusResponse(BaseResponse[FolderScheduleStatusData]):
    """调度状态响应 - 返回 7 字段的调度状态"""
    ...
