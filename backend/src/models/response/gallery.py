"""
图库相关响应模型
"""

from typing import Optional, List

from pydantic import BaseModel, Field

from src.models.response.base_response import BaseResponse


class ImageDetail(BaseModel):
    """图片详情"""

    id: int
    tags: List[str]
    width: int
    height: int
    rating: str
    file_url: str
    preview_url: str
    sample_url: Optional[str]
    file_size: int
    file_ext: str
    author: str
    created_at: str
    md5: str
    score: Optional[int]
    is_downloaded: bool = Field(description="是否已下载")
    local_preview_path: Optional[str] = Field(None, description="本地预览图路径")
    local_file_path: Optional[str] = Field(None, description="本地原图路径")


class GalleryData(BaseModel):
    """图库数据"""

    total: int
    page: int
    page_size: int
    has_more: bool
    images: List[ImageDetail]


class GalleryLoadResponse(BaseResponse[GalleryData]):
    """图库加载响应"""

    ...


class ImageDetailResponse(BaseResponse[ImageDetail]):
    """图片详情响应"""

    ...
