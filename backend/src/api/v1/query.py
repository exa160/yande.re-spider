"""
查询相关API路由
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum

router = APIRouter()


class RatingFilter(str, Enum):
    SAFE = "Safe"
    QUESTIONABLE = "Questionable"
    EXPLICIT = "Explicit"
    ALL = "All"


class SortBy(str, Enum):
    CREATED_AT = "created_at"
    RATING = "rating"
    FILE_SIZE = "file_size"
    WIDTH = "width"
    HEIGHT = "height"


class SortOrder(str, Enum):
    ASC = "asc"
    DESC = "desc"


class QueryParams(BaseModel):
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


class ImageData(BaseModel):
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


class QueryResponse(BaseModel):
    total: int = Field(description="总数")
    page: int = Field(description="当前页")
    page_size: int = Field(description="每页数量")
    images: List[ImageData] = Field(description="图片列表")


@router.post("/search", response_model=QueryResponse, summary="高级查询")
async def advanced_search(params: QueryParams):
    try:
        return QueryResponse(
            total=0, page=params.page, page_size=params.page_size, images=[]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.get("/presets", summary="获取查询预设列表")
async def get_query_presets():
    return {"presets": []}


@router.post("/presets", summary="保存查询预设")
async def save_query_preset(name: str, params: QueryParams):
    return {"message": "预设保存成功", "name": name}


@router.delete("/presets/{preset_id}", summary="删除查询预设")
async def delete_query_preset(preset_id: int):
    return {"message": "预设删除成功"}
