from typing import Optional

from pydantic import BaseModel, Field, field_validator


class FavoriteFolderUpdate(BaseModel):
    """更新收藏夹请求模型"""

    name: Optional[str] = Field(None, min_length=1, max_length=50)
    tags: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    sort_order: Optional[int] = None
    schedule_enabled: Optional[bool] = None
    schedule_cron: Optional[str] = Field(None, max_length=64)
    schedule_mode: Optional[str] = Field(None, max_length=16)
    schedule_max_images: Optional[int] = Field(None, ge=1)

    @field_validator("schedule_mode")
    @classmethod
    def _validate_mode(cls, v):
        if v is not None and v not in ("last_id", "max"):
            raise ValueError("schedule_mode must be 'last_id' or 'max'")
        return v


class FavoriteFolderBase(BaseModel):
    """收藏夹基础模型"""

    name: str = Field(..., min_length=1, max_length=50, description="收藏夹名称")
    tags: str = Field(default="", description="查询标签字符串，如 rating:s score:>100")
    color: str = Field(default="#409EFF", description="展示颜色，hex格式")
    icon: str = Field(default="folder", description="图标标识")
    sort_order: int = Field(default=0, description="排序权重")
    schedule_enabled: bool = Field(default=False, description="是否启用定时调度")
    schedule_cron: str = Field(default="", max_length=64, description="cron 表达式")
    schedule_mode: str = Field(default="last_id", description="last_id | max")
    schedule_max_images: Optional[int] = Field(default=None, ge=1, description="单次最大下载数（None 用全局默认）")

    @field_validator("schedule_mode")
    @classmethod
    def _validate_mode(cls, v):
        if v not in ("last_id", "max"):
            raise ValueError("schedule_mode must be 'last_id' or 'max'")
        return v


class FavoriteFolderCreate(FavoriteFolderBase):
    """创建收藏夹请求模型"""
    pass



class ReorderRequest(BaseModel):
    """批量更新排序请求模型"""

    folder_ids: list[int] = Field(..., description="按新顺序排列的收藏夹ID列表")


class LastSyncedIdResetRequest(BaseModel):
    """重置 last_synced_id 请求模型。不传 value 表示清空（下次回到首次行为）。"""

    value: Optional[int] = Field(default=None, ge=0, description="重置后的 last_synced_id，null/缺省表示清空")