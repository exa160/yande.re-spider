"""MyFavorites 响应模型"""
from typing import List, Optional

from loguru import logger
from pydantic import BaseModel, Field, field_serializer, field_validator

from src.common.constant import Rating

# display 字符串 → Rating 的反向映射（'Safe'→S, 'Questionable'→R15, 'Explicit'→R18）。
# 供 coerce_rating 容错：service 层已按项目约定调用 .display 传入 display 字符串，
# 模型层仍需把它还原成 Rating 枚举，再经 serialize_rating 输出 display。
_DISPLAY_TO_RATING = {r.display: r for r in Rating}


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
    """预览图元数据（结构对齐 FavoriteFolderWithMinimalPreview.preview_images）。

    rating 字段：与主视图 / 收藏夹预览契约一致——
    - 入参容错：字符串 's'/'q'/'e'、Rating 枚举、未知值、None / 空串均可接受
      （未知值降级为 Rating.R15/q，与 ``FolderPreviewImageMinimal.coerce_rating`` 一致）
    - 序列化输出：Rating.display（'Safe'/'Questionable'/'Explicit'），
      而非数据库原值（'s'/'q'/'e'）。
    原因：前端 ``FolderTile.vue`` / ``WaterfallGallery.vue`` / ``Gallery.vue``
    的 safeMode 模糊判断与 ``getRatingType`` 字典都按 'Safe' / 'Questionable' /
    'Explicit' 比较；如果接口返回 's'，则 !== 'Safe' 永远为 true → 安全模式
    下整个我的最爱预览图全模糊。
    """
    id: int = Field(...)
    preview_url: Optional[str] = Field(default=None)
    tags: str = Field(default="")
    rating: Optional[Rating] = Field(default=None, description="图片评级（s/q/e）")

    @field_validator('rating', mode='before')
    @classmethod
    def coerce_rating(cls, v):
        """None/空串/Rating 枚举/数据库原值 's'/'q'/'e'/display 字符串 → Rating 枚举。

        容错：未知值降级为 Rating.R15（q），与 FolderPreviewImageMinimal 一致。
        同时接受 display 字符串，使 service 层预先调用 .display 后仍能正确还原。
        """
        if v is None or v == '':
            return None
        if isinstance(v, Rating):
            return v
        try:
            return Rating(v)
        except ValueError:
            pass
        if v in _DISPLAY_TO_RATING:
            return _DISPLAY_TO_RATING[v]
        logger.warning(f"Unknown rating value: {v!r}, defaulting to Rating.R15 (q)")
        return Rating.R15

    @field_serializer('rating')
    def serialize_rating(self, v: Optional[Rating]) -> str:
        """Rating 枚举 → display 字符串（'Safe'/'Questionable'/'Explicit'）；None → ""。"""
        if v is None:
            return ""
        return v.display


class MyFavoritePreviewResponse(BaseModel):
    """我的最爱预览响应"""
    images: List[MyFavoritePreviewImage] = Field(default_factory=list)
