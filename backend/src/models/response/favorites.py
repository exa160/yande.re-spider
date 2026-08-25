
from datetime import datetime
from typing import Optional

from loguru import logger
from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from src.common.constant import Rating
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


class FolderPreviewImageMinimal(BaseModel):
    """收藏夹瀑布流用的精简预览元数据（不含 URL，前端自行拼 /api/v1/gallery/cache/preview/{id}）。

    rating 字段：与主视图 ImageDetail 一致，序列化输出 Rating.display（'Safe'/'Questionable'/'Explicit'），
    而非数据库原值（'s'/'q'/'e'）。原因：前端 FolderTile.vue 的 safeMode 模糊判断是按 'Safe' 比较的，
    如果接口返回 's'，则 !== 'Safe' 永远为 true → 安全模式下整个收藏夹预览图全模糊。
    """
    id: int
    width: Optional[int] = None
    height: Optional[int] = None
    rating: Optional[Rating] = Field(default=None, description="图片评级（s/q/e）")
    model_config = ConfigDict(from_attributes=True)

    @field_validator('rating', mode='before')
    @classmethod
    def coerce_rating(cls, v):
        """数据库字符串 → Rating 枚举（容错：未知值降级为 R15=q）。"""
        if v is None or v == '':
            return None
        if isinstance(v, Rating):
            return v
        try:
            return Rating(v)
        except ValueError:
            logger.warning(f"Unknown rating value: {v!r}, defaulting to Rating.R15 (q)")
            return Rating.R15

    @field_serializer('rating')
    def serialize_rating(self, v: Optional[Rating]) -> Optional[str]:
        """Rating 枚举 → display 字符串（'Safe'/'Questionable'/'Explicit'）。"""
        if v is None:
            return None
        return v.display


class FavoriteFolderWithMinimalPreview(FavoriteFolder):
    """带精简预览图的收藏夹模型（瀑布流场景）。"""
    preview_images: list[FolderPreviewImageMinimal] = Field(
        default_factory=list, description="预览图片元数据（仅 id/width/height/rating）"
    )


class FavoriteFoldersWithPreviewListData(BaseModel):
    """带预览的收藏夹列表响应数据。"""
    items: list[FavoriteFolderWithMinimalPreview]
    total: int
    has_more: bool


# ============================================
# Data sub-models (嵌套用，Pydantic 自动校验)
# ============================================

class FolderCountData(BaseModel):
    """收藏夹数量更新（在线/本地）的 data 模型"""
    count: int = Field(..., description="更新后的数量值")


class PreviewImage(BaseModel):
    """预览图片（接受 YandeData ORM 对象）。

    rating 字段同样走 Rating 枚举 + display 序列化，与主视图保持一致，
    避免后续『我的最爱』全量预览功能踩同样的坑。
    """
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
    rating: Optional[Rating] = Field(default=None, description="图片评级（s/q/e）")

    model_config = ConfigDict(from_attributes=True)

    @field_validator('rating', mode='before')
    @classmethod
    def coerce_rating(cls, v):
        if v is None or v == '':
            return None
        if isinstance(v, Rating):
            return v
        try:
            return Rating(v)
        except ValueError:
            logger.warning(f"Unknown rating value: {v!r}, defaulting to Rating.R15 (q)")
            return Rating.R15

    @field_serializer('rating')
    def serialize_rating(self, v: Optional[Rating]) -> Optional[str]:
        if v is None:
            return None
        return v.display


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


class FavoriteFoldersWithPreviewResponse(BaseResponse[FavoriteFoldersWithPreviewListData]):
    """查询响应 - 带图片预览的收藏夹详情列表（items + total + has_more）"""
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
