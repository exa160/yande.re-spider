"""
标签缓存业务逻辑层
"""

from typing import List, Optional, Tuple

from loguru import logger

from src.dao import TagRepository, ArtistRepository
from src.dao.download_task_dao import DownloadTaskDao
from src.infrastructure.yande_api import YandeApi

# 全量本地统计要求下载队列连续空闲的时长（秒）。
# 全量重算是「读全表 → 聚合 → 批量写」，与下载/在线扫描并发会放大 SQLite 锁竞争，
# 也容易把下载期间的增量变更覆盖掉；空闲 5 分钟后才允许跑。
TAG_STATS_MIN_IDLE_SECONDS = 300


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

        tags = yande_api.get_tags(limit=0)
        if tags:
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

        if not current_after_id:
            logger.info("Tag cache is empty, switching to full refresh")
            return TagCacheService._full_refresh_tags(yande_api)

        logger.info(f"增量更新，从最大ID {current_after_id} 开始")

        while has_more:
            tags = yande_api.get_tags(limit=limit, after_id=current_after_id)
            if not tags:
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
                artists = yande_api.get_artists(page=current_page)
                if not artists:
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
    def calculate_local_stats(
        min_idle_seconds: float = TAG_STATS_MIN_IDLE_SECONDS,
    ) -> dict:
        """全量重算本地标签统计（带两道门禁）。

        1. 下载队列需连续空闲 ``min_idle_seconds``（默认 5 分钟）：避免全表扫描
           与下载写入并发（SQLite 下尤其重要），也避免统计期间数据继续变化。
        2. 最近一次下载完成时间不晚于上次全量计算时间时直接跳过：没有新数据
           就没必要重扫 3 万+ 图片。

        Returns:
            {
                "success": True,
                "calculated": bool,          # 是否真的执行了重算
                "skipped": Optional[str],    # download_busy / up_to_date
                "tags_updated": int,
                "idle_seconds": float,       # 判定时的队列空闲时长
                "min_idle_seconds": float,
            }
        """
        # 延迟导入：download_queue 属于 infrastructure，避免模块加载期建立反向依赖
        from src.infrastructure.download_queue import download_queue

        idle_seconds = download_queue.get_idle_seconds()
        base = {
            "success": True,
            "calculated": False,
            "skipped": None,
            "tags_updated": 0,
            "idle_seconds": round(idle_seconds, 1),
            "min_idle_seconds": float(min_idle_seconds),
        }

        if idle_seconds < min_idle_seconds:
            base["skipped"] = "download_busy"
            logger.info(
                f"Local stats skipped: queue idle {idle_seconds:.0f}s "
                f"< {min_idle_seconds:.0f}s"
            )
            return base

        with DownloadTaskDao() as download_task_dao:
            latest_completed = download_task_dao.max_completed_at()

        with TagRepository() as repo:
            last_calculated = repo.get_local_stats_last_calculated()
            # 没有任何 stats 行（首次）→ 必须算；有记录且不早于最近下载 → 跳过
            if last_calculated is not None and (
                latest_completed is None or last_calculated >= latest_completed
            ):
                base["skipped"] = "up_to_date"
                logger.info("Local stats skipped: already up to date")
                return base

            stats_updated = repo.calculate_local_stats()

        base["calculated"] = True
        base["tags_updated"] = stats_updated
        logger.info(f"Local stats calculated: {stats_updated} tags updated")
        return base

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
