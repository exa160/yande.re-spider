"""
图库相关请求模型
"""

from typing import Optional, List

from pydantic import BaseModel, Field

from src.common.constant import CleanupMode, Rating
from src.dao.yande_data_dao import SortBy, SortOrder


class GalleryLoadRequest(BaseModel):
    """图库加载请求"""

    page: int = Field(1, ge=1, description="页码")
    page_size: int = Field(25, ge=1, le=50, description="每页数量")
    tags: Optional[str] = Field(None, description="标签过滤")
    user: Optional[str] = Field(None, description="用户过滤: user:bob")
    vote: Optional[int] = Field(None, description="投票数过滤: vote:3")
    md5: Optional[str] = Field(None, description="MD5哈希过滤")
    source: Optional[str] = Field(None, description="来源过滤: source:http://site.com")
    rating: Optional[List[Rating]] = Field(None, description="评分过滤列表")
    author: Optional[str] = Field(None, description="作者过滤")
    min_id: Optional[int] = Field(None, description="最小ID: id:>=100")
    max_id: Optional[int] = Field(None, description="最大ID: id:<=100")
    min_width: Optional[int] = Field(None, description="最小宽度")
    max_width: Optional[int] = Field(None, description="最大宽度")
    min_height: Optional[int] = Field(None, description="最小高度")
    max_height: Optional[int] = Field(None, description="最大高度")
    min_mpixels: Optional[float] = Field(
        None, description="最小像素(百万): mpixels:>=2.5"
    )
    max_mpixels: Optional[float] = Field(None, description="最大像素(百万)")
    ratio: Optional[str] = Field(None, description="宽高比: ratio:16:9")
    min_date: Optional[str] = Field(None, description="最早日期: date:>=2007-01-01")
    max_date: Optional[str] = Field(None, description="最晚日期: date:<=2007-01-01")
    min_file_size: Optional[int] = Field(None, description="最小文件大小(KB)")
    max_file_size: Optional[int] = Field(None, description="最大文件大小(KB)")
    file_types:  Optional[List[str]] = Field(None, description="文件类型列表")
    min_score: Optional[int] = Field(None, description="最小评分")
    max_score: Optional[int] = Field(None, description="最大评分")
    # 排序: id, id_desc, score, score_asc, mpixels, mpixels_asc, landscape, portrait, vote
    sort_by: str = Field(SortBy.ID, description="排序字段")
    sort_order: str = Field(SortOrder.DESC, description="排序方向: asc/desc")
    parent_id: Optional[int] = Field(None, description="父贴ID: parent:1234")
    parent_none: bool = Field(False, description="无父贴: parent:none")
    source: Optional[str] = Field(
        "local",
        description="数据源: yande=在线, local=本地数据库, favorites=收藏夹（用 favorite_id 定位）",
    )
    favorite_id: Optional[int] = Field(
        None, description="source='favorites' 时定位收藏夹的 ID"
    )
    include_online: bool = Field(
        False,
        description="source='favorites' 时是否同时合并在线内容（与 local 去重合并）",
    )


class CleanupPreviewsRequest(BaseModel):
    """预览图清理请求"""

    mode: CleanupMode = Field(
        ...,
        description=(
            "clean_local_previews: 仅清有原图可再生的 preview；"
            "clean_all_previews: 清空整个 previews/ 目录"
        ),
    )
    dry_run: bool = Field(
        True,
        description="True 时仅评估不删除；False 时执行实际删除",
    )
