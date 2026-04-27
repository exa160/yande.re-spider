from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional
from loguru import logger

from backend.infrastructure.yande_api import YandeApi
from backend.dao.yande_data import TagRepository, ArtistRepository


router = APIRouter()


class RefreshTagsRequest(BaseModel):
    full_refresh: bool = Field(False, description="是否全量更新（limit=0获取全部）")
    limit: int = Field(100, ge=0, le=1000, description="每页数量，0表示获取全部")


class RefreshArtistsRequest(BaseModel):
    page: int = Field(1, ge=1, description="起始页码")
    limit: int = Field(100, ge=1, le=1000, description="每页数量")
    max_pages: int = Field(10, ge=1, description="最大页数")


class TagInfo(BaseModel):
    id: int
    name: str
    count: int
    type: int
    ambiguous: bool


class TagInfoWithStats(BaseModel):
    id: int
    name: str
    count: int
    type: int
    ambiguous: bool
    local_count: int = 0


class ArtistInfo(BaseModel):
    id: int
    name: str
    alias_id: Optional[int]
    group_id: Optional[int]
    urls: List[str]


@router.post("/refresh-tags", summary="从 yande.re 刷新标签缓存")
async def refresh_tags(request: RefreshTagsRequest):
    """从 yande.re API 批量获取标签并入库缓存，支持全量和增量更新"""
    yande_api = YandeApi()
    total_updated = 0
    has_more = True

    try:
        if request.full_refresh:
            with TagRepository() as repo:
                repo.clear_all_tags()
            success, tags = yande_api.get_tags(limit=0)
            if success and tags:
                with TagRepository() as repo:
                    total_updated = repo.upsert_tags(tags)
                last_id = max(t["id"] for t in tags) if tags else 0
                logger.info(
                    f"全量刷新完成: 获取 {len(tags)} 标签，更新 {total_updated} 条"
                )
                return {
                    "success": True,
                    "total_updated": total_updated,
                    "last_id": last_id,
                }
            return {"success": False, "total_updated": 0, "last_id": 0}

        with TagRepository() as repo:
            current_after_id = repo.get_max_id()
            logger.info(f"增量更新，从最大ID {current_after_id} 开始")

        while has_more:
            success, tags = yande_api.get_tags(
                limit=request.limit, after_id=current_after_id
            )
            if not success or not tags:
                logger.warning(f"Failed to fetch tags after_id {current_after_id}")
                break

            with TagRepository() as repo:
                updated = repo.upsert_tags(tags)
                total_updated += updated

            if tags:
                current_after_id = max(t["id"] for t in tags)
                logger.info(
                    f"Fetched {len(tags)} tags, last id {current_after_id}, updated {updated}"
                )

            if len(tags) < request.limit:
                has_more = False

        return {
            "success": True,
            "total_updated": total_updated,
            "last_id": current_after_id,
        }
    except Exception as e:
        logger.error(f"Refresh tags error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/refresh-artists", summary="从 yande.re 刷新艺术家缓存")
async def refresh_artists(request: RefreshArtistsRequest):
    """从 yande.re API 批量获取艺术家并入库缓存"""
    yande_api = YandeApi()
    total_updated = 0
    current_page = request.page
    pages_done = 0

    try:
        while pages_done < request.max_pages:
            success, artists = yande_api.get_artists(
                page=current_page, limit=request.limit
            )
            if not success or not artists:
                logger.warning(f"Failed to fetch artists at page {current_page}")
                break

            with ArtistRepository() as repo:
                updated = repo.upsert_artists(artists)
                total_updated += updated

            logger.info(f"Page {current_page}: updated {updated} artists")
            pages_done += 1
            current_page += 1

            if len(artists) < request.limit:
                break

        return {
            "success": True,
            "total_updated": total_updated,
            "pages_done": pages_done,
        }
    except Exception as e:
        logger.error(f"Refresh artists error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tags/stats", summary="获取标签缓存统计")
async def get_tags_stats():
    """获取本地标签缓存的统计信息"""
    try:
        with TagRepository() as repo:
            total = repo.get_tag_count()
            max_id = repo.get_max_id()
        return {"total": total, "max_id": max_id}
    except Exception as e:
        logger.error(f"Get tags stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/artists/stats", summary="获取艺术家缓存统计")
async def get_artists_stats():
    """获取本地艺术家缓存的统计信息"""
    try:
        with ArtistRepository() as repo:
            total = repo.get_artist_count()
        return {"total": total}
    except Exception as e:
        logger.error(f"Get artists stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tags/search", response_model=List[TagInfo], summary="搜索标签")
async def search_tags(keyword: str, limit: int = 20):
    """从本地缓存搜索标签"""
    try:
        with TagRepository() as repo:
            results = repo.search_tags(keyword, limit)
        return results
    except Exception as e:
        logger.error(f"Search tags error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/artists/search", response_model=List[ArtistInfo], summary="搜索艺术家")
async def search_artists(keyword: str, limit: int = 20):
    """从本地缓存搜索艺术家"""
    try:
        with ArtistRepository() as repo:
            results = repo.search_artists(keyword, limit)
        return results
    except Exception as e:
        logger.error(f"Search artists error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tags/calculate-local-stats", summary="计算本地标签统计")
async def calculate_local_stats():
    """从本地已下载图片计算每个标签的使用次数并存储到 tag_local_stats 表"""
    try:
        with TagRepository() as repo:
            stats_updated = repo.calculate_local_stats()
        logger.info(f"Local stats calculated: {stats_updated} tags updated")
        return {"success": True, "tags_updated": stats_updated}
    except Exception as e:
        logger.error(f"Calculate local stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tags/with-stats", summary="获取标签列表（带本地统计）")
async def get_tags_with_stats(
    type: Optional[int] = None,
    search: Optional[str] = None,
    limit: int = 100,
    has_local_only: bool = False,
):
    """获取标签列表，包含 yande.re 远程数量和本地使用数量"""
    try:
        with TagRepository() as repo:
            tags, total = repo.get_tags_with_stats(
                tag_type=type,
                search_keyword=search,
                limit=limit,
                has_local_only=has_local_only,
            )
        return {"tags": tags, "total": total}
    except Exception as e:
        logger.error(f"Get tags with stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tags/by-names", summary="根据名称批量获取标签类型")
async def get_tags_by_names(names: str):
    """根据逗号分隔的 tag 名称字符串返回类型信息"""
    try:
        name_list = [n.strip() for n in names.split(",") if n.strip()]
        if not name_list:
            return {}

        with TagRepository() as repo:
            result = repo.get_tags_by_names(name_list)
        return result
    except Exception as e:
        logger.error(f"Get tags by names error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
