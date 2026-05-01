"""
查询相关响应模型
"""

from typing import List

from pydantic import BaseModel, Field

from src.models.response.base_response import BaseResponse


class ImageData(BaseModel):
    """图片数据"""

    id: int
    tags: List[str]
    width: int
    height: int
    rating: str
    file_url: str
    preview_url: str
    file_size: int
    author: str
    created_at: str
    md5: str


class QueryData(BaseModel):
    """查询数据"""

    total: int = Field(description="总数")
    page: int = Field(description="当前页")
    page_size: int = Field(description="每页数量")
    images: List[ImageData] = Field(description="图片列表")


class QueryResponse(BaseResponse[QueryData]):
    """查询响应"""

    ...
