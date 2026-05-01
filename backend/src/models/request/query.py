"""
查询相关请求模型
"""

from typing import Optional
from enum import Enum

from pydantic import BaseModel, Field


class RatingFilter(str, Enum):
    """评分过滤枚举"""

    SAFE = "Safe"
    QUESTIONABLE = "Questionable"
    EXPLICIT = "Explicit"
    ALL = "All"


class SortBy(str, Enum):
    """排序字段枚举"""

    CREATED_AT = "created_at"
    RATING = "rating"
    FILE_SIZE = "file_size"
    WIDTH = "width"
    HEIGHT = "height"


class SortOrder(str, Enum):
    """排序方向枚举"""

    ASC = "asc"
    DESC = "desc"


class QueryParams(BaseModel):
    """高级查询参数"""

    tags: Optional[str] = Field(
        None, description="标签表达式，支持AND/OR/NOT逻辑运算符"
    )
    min_width: Optional[int] = Field(None, ge=0, le=10000, description="最小宽度")
    max_width: Optional[int] = Field(None, ge=0, le=10000, description="最大宽度")
    min_height: Optional[int] = Field(None, ge=0, le=10000, description="最小高度")
    max_height: Optional[int] = Field(None, ge=0, le=10000, description="最大高度")
    rating: Optional[RatingFilter] = Field(RatingFilter.ALL, description="评分过滤")
    min_file_size: Optional[int] = Field(
        None, ge=0, le=1000000, description="最小文件大小(KB)"
    )
    max_file_size: Optional[int] = Field(
        None, ge=0, le=1000000, description="最大文件大小(KB)"
    )
    file_type: Optional[str] = Field(None, description="文件类型(JPG/PNG/GIF/WEBP)")
    author: Optional[str] = Field(None, max_length=100, description="作者名称")
    sort_by: Optional[SortBy] = Field(SortBy.CREATED_AT, description="排序字段")
    sort_order: Optional[SortOrder] = Field(SortOrder.DESC, description="排序方向")
    page: int = Field(1, ge=1, description="页码")
    page_size: int = Field(20, ge=1, le=100, description="每页数量")
