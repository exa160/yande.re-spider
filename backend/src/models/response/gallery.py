"""
图库相关响应模型
"""

from datetime import datetime
from typing import Optional, List

from pydantic import (
    BaseModel, ConfigDict, Field,
    FieldSerializationInfo, field_serializer, field_validator
)

from src.common.constant import Rating
from src.common.utils import check_local_file
from src.models.response.base_response import BaseResponse, PaginatedResponse


class ImageDetail(BaseModel):
    """图片详情"""

    id: int = Field(description="图片ID")
    tags: List[str] = Field(description="图片标签列表")
    width: int = Field(description="图片宽度")
    height: int = Field(description="图片高度")
    rating: Rating = Field(description="图片评级，如 S/R18")
    file_url: str = Field(description="图片文件URL，仅返回本地路径")
    preview_url: str = Field(description="预览图URL，仅返回本地路径")
    file_size: int = Field(description="文件大小，单位字节")
    file_ext: str = Field(description="文件扩展名，如 jpg/png")
    author: str = Field(description="上传者")
    created_at: datetime = Field(description="创建时间")
    md5: str = Field(description="MD5 哈希值")
    score: Optional[int] = Field(description="评分")
    down_flag: bool = Field(description="是否已下载")

    model_config = ConfigDict(from_attributes=True)

    @field_validator('tags', mode='before')
    def normalize_tags(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            return v.split()
        if isinstance(v, (list, tuple)):
            return list(v)
        raise ValueError('tags must be a string or list of strings')

    @field_serializer('file_url', 'preview_url')
    def serialize_dt(self, _: str, info: FieldSerializationInfo) -> str:
        return check_local_file(self.id, self.file_ext, info.field_name.split('_')[0])
    
    @field_serializer('rating')
    def serialize_rating(self, v: Rating) -> str:
        return v.display   # 输出 "Safe"/"Questionable"/"Explicit"


class GalleryLoadResponse(PaginatedResponse[List[ImageDetail]]):
    """图库加载响应"""
    has_more: bool = Field(description="下一页")


class ImageDetailResponse(BaseResponse[ImageDetail]):
    """图片详情响应"""

    ...
