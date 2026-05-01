"""
标签缓存 API 路由
"""

from fastapi import APIRouter
from typing import Optional

from src.common.constant import ErrMsg
from src.middleware.errors import APIException
from src.models.request.tag_cache import RefreshTagsRequest, RefreshArtistsRequest
from src.models.response.base_response import BaseResponse
from src.models.response.tag_cache import TagInfo, ArtistInfo
from src.services.tag_cache import TagCacheService

router = APIRouter()


@router.post(
    "/refresh-tags", response_model=BaseResponse, summary="从 yande.re 刷新标签缓存"
)
async def refresh_tags(request: RefreshTagsRequest) -> BaseResponse:
    """从 yande.re API 批量获取标签并入库缓存，支持全量和增量更新"""
    try:
        result = TagCacheService.refresh_tags(
            limit=request.limit, full_refresh=request.full_refresh
        )
        return BaseResponse(message="刷新成功", data=result)
    except Exception as e:
        raise APIException(ErrMsg.UPDATE_ERROR, e=e)


@router.post(
    "/refresh-artists",
    response_model=BaseResponse,
    summary="从 yande.re 刷新艺术家缓存",
)
async def refresh_artists(request: RefreshArtistsRequest) -> BaseResponse:
    """从 yande.re API 批量获取艺术家并入库缓存"""
    try:
        result = TagCacheService.refresh_artists(
            limit=request.limit, page=request.page, max_pages=request.max_pages
        )
        return BaseResponse(message="刷新成功", data=result)
    except Exception as e:
        raise APIException(ErrMsg.UPDATE_ERROR, e=e)


@router.get("/tags/stats", response_model=BaseResponse, summary="获取标签缓存统计")
async def get_tags_stats() -> BaseResponse:
    """获取本地标签缓存的统计信息"""
    try:
        stats = TagCacheService.get_tags_stats()
        return BaseResponse(message=ErrMsg.OK.msg, data=stats)
    except Exception as e:
        raise APIException(ErrMsg.QUERY_ERROR, e=e)


@router.get("/artists/stats", response_model=BaseResponse, summary="获取艺术家缓存统计")
async def get_artists_stats() -> BaseResponse:
    """获取本地艺术家缓存的统计信息"""
    try:
        stats = TagCacheService.get_artists_stats()
        return BaseResponse(message=ErrMsg.OK.msg, data=stats)
    except Exception as e:
        raise APIException(ErrMsg.QUERY_ERROR, e=e)


@router.get("/tags/search", response_model=BaseResponse, summary="搜索标签")
async def search_tags(keyword: str, limit: int = 20) -> BaseResponse:
    """从本地缓存搜索标签"""
    try:
        tags = TagCacheService.search_tags(keyword, limit)
        return BaseResponse(message=ErrMsg.OK.msg, data=tags)
    except Exception as e:
        raise APIException(ErrMsg.QUERY_ERROR, e=e)


@router.get("/artists/search", response_model=BaseResponse, summary="搜索艺术家")
async def search_artists(keyword: str, limit: int = 20) -> BaseResponse:
    """从本地缓存搜索艺术家"""
    try:
        artists = TagCacheService.search_artists(keyword, limit)
        return BaseResponse(message=ErrMsg.OK.msg, data=artists)
    except Exception as e:
        raise APIException(ErrMsg.QUERY_ERROR, e=e)


@router.post(
    "/tags/calculate-local-stats",
    response_model=BaseResponse,
    summary="计算本地标签统计",
)
async def calculate_local_stats() -> BaseResponse:
    """从本地已下载图片计算每个标签的使用次数并存储到 tag_local_stats 表"""
    try:
        stats_updated = TagCacheService.calculate_local_stats()
        return BaseResponse(
            message="计算完成", data={"success": True, "tags_updated": stats_updated}
        )
    except Exception as e:
        raise APIException(ErrMsg.UPDATE_ERROR, e=e)


@router.get(
    "/tags/with-stats",
    response_model=BaseResponse,
    summary="获取标签列表（带本地统计）",
)
async def get_tags_with_stats(
    type: Optional[int] = None,
    search: Optional[str] = None,
    limit: int = 100,
    has_local_only: bool = False,
) -> BaseResponse:
    """获取标签列表，包含 yande.re 远程数量和本地使用数量"""
    try:
        tags, total = TagCacheService.get_tags_with_stats(
            tag_type=type,
            search=search,
            limit=limit,
            has_local_only=has_local_only,
        )
        return BaseResponse(message=ErrMsg.OK.msg, data={"tags": tags, "total": total})
    except Exception as e:
        raise APIException(ErrMsg.QUERY_ERROR, e=e)


@router.get(
    "/tags/by-names", response_model=BaseResponse, summary="根据名称批量获取标签类型"
)
async def get_tags_by_names(names: str) -> BaseResponse:
    """根据逗号分隔的 tag 名称字符串返回类型信息"""
    try:
        name_list = [n.strip() for n in names.split(",") if n.strip()]
        result = TagCacheService.get_tags_by_names(name_list)
        return BaseResponse(message=ErrMsg.OK.msg, data=result)
    except Exception as e:
        raise APIException(ErrMsg.QUERY_ERROR, e=e)
