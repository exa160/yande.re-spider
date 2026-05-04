"""
标签缓存业务逻辑层
"""

from typing import List, Optional, Tuple

from loguru import logger

from src.dao.yande_data import TagRepository, ArtistRepository
from src.infrastructure.yande_api import YandeApi


class TagCacheService:
    """标签缓存服务类"""

    @staticmethod
    def refresh_tags(limit: int = 100, full_refresh: bool = False) -> dict:
        """
        从 yande.re API 刷新标签缓存

        Args:
            limit: 每次请求的数量
            full_refresh: 是否全量刷新

        Returns:
            {"success": bool, "total_updated": int, "last_id": int}
        """
        yande_api = YandeApi()

        try:
            if full_refresh:
                return TagCacheService._full_refresh_tags(yande_api)
            else:
                return TagCacheService._incremental_refresh_tags(yande_api, limit)
        except Exception as e:
            logger.error(f"Refresh tags error: {e}")
            raise

    @staticmethod
    def _full_refresh_tags(yande_api: YandeApi) -> dict:
        """全量刷新标签"""
        with TagRepository() as repo:
            repo.clear_all_tags()

        success, tags = yande_api.get_tags(limit=0)
        if success and tags:
            with TagRepository() as repo:
                total_updated = repo.upsert_tags(tags)
            last_id = max(t["id"] for t in tags) if tags else 0
            logger.info(f"全量刷新完成: 获取 {len(tags)} 标签，更新 {total_updated} 条")
            return {"success": True, "total_updated": total_updated, "last_id": last_id}

        return {"success": False, "total_updated": 0, "last_id": 0}

    @staticmethod
    def _incremental_refresh_tags(yande_api: YandeApi, limit: int) -> dict:
        """增量刷新标签"""
        total_updated = 0
        has_more = True

        with TagRepository() as repo:
            current_after_id = repo.get_max_id()

        if not current_after_id or current_after_id == 0:
            logger.info("Tag cache is empty, switching to full refresh")
            return TagCacheService._full_refresh_tags(yande_api)

        logger.info(f"增量更新，从最大ID {current_after_id} 开始")

        while has_more:
            success, tags = yande_api.get_tags(limit=limit, after_id=current_after_id)
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

            if len(tags) < limit:
                has_more = False

        return {
            "success": True,
            "total_updated": total_updated,
            "last_id": current_after_id,
        }

    @staticmethod
    def refresh_artists(page: int = 1, max_pages: int = 10) -> dict:
        """
        从 yande.re API 刷新艺术家缓存

        Args:
            page: 起始页码
            max_pages: 最大页数

        Returns:
            {"success": bool, "total_updated": int, "pages_done": int}
        """
        yande_api = YandeApi()
        total_updated = 0
        current_page = page
        pages_done = 0

        try:
            while pages_done < max_pages:
                success, artists = yande_api.get_artists(page=current_page)
                if not success or not artists:
                    logger.warning(f"Failed to fetch artists at page {current_page}")
                    break

                with ArtistRepository() as repo:
                    updated = repo.upsert_artists(artists)
                    total_updated += updated

                logger.info(f"Page {current_page}: updated {updated} artists")
                pages_done += 1
                current_page += 1

                if len(artists) < 25:
                    break

            return {
                "success": True,
                "total_updated": total_updated,
                "pages_done": pages_done,
            }
        except Exception as e:
            logger.error(f"Refresh artists error: {e}")
            raise

    @staticmethod
    def get_tags_stats() -> dict:
        """获取本地标签缓存的统计信息"""
        with TagRepository() as repo:
            total = repo.get_tag_count()
            max_id = repo.get_max_id()
        return {"total": total, "max_id": max_id}

    @staticmethod
    def get_artists_stats() -> dict:
        """获取本地艺术家缓存的统计信息"""
        with ArtistRepository() as repo:
            total = repo.get_artist_count()
        return {"total": total}

    @staticmethod
    def search_tags(keyword: str, limit: int = 20) -> List[dict]:
        """从本地缓存搜索标签"""
        with TagRepository() as repo:
            return repo.search_tags(keyword, limit)

    @staticmethod
    def search_artists(keyword: str, limit: int = 20) -> List[dict]:
        """从本地缓存搜索艺术家"""
        with ArtistRepository() as repo:
            return repo.search_artists(keyword, limit)

    @staticmethod
    def calculate_local_stats() -> int:
        """计算本地标签统计"""
        with TagRepository() as repo:
            stats_updated = repo.calculate_local_stats()
        logger.info(f"Local stats calculated: {stats_updated} tags updated")
        return stats_updated

    @staticmethod
    def get_tags_with_stats(
        tag_type: Optional[int] = None,
        search: Optional[str] = None,
        limit: int = 100,
        has_local_only: bool = False,
    ) -> Tuple[List[dict], int]:
        """获取标签列表，包含 yande.re 远程数量和本地使用数量"""
        with TagRepository() as repo:
            return repo.get_tags_with_stats(
                tag_type=tag_type,
                search_keyword=search,
                limit=limit,
                has_local_only=has_local_only,
            )

    @staticmethod
    def get_tags_by_names(names: List[str]) -> dict:
        """根据名称批量获取标签类型"""
        if not names:
            return {}
        with TagRepository() as repo:
            return repo.get_tags_by_names(names)
