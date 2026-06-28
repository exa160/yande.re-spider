from __future__ import annotations

import asyncio
import time
from datetime import datetime
from typing import Optional

from loguru import logger

from src.common import config
from src.dao.favorite_dao import FavoriteDao
from src.dao.yande_data_dao import YandeDataRepository
from src.infrastructure.yande_api import YandeApi
from src.services.download import DownloadService
from src.services.favorites import FavoritesService


_schedule_semaphore = asyncio.Semaphore(
    config.scheduler.max_concurrent_schedules
)


async def run_folder_schedule(folder_id: int) -> dict:
    async with _schedule_semaphore:
        with FavoriteDao() as dao:
            folder = dao.get_by_id(folder_id)
            if not folder:
                logger.warning(f"Folder {folder_id} not found, skip")
                return {"skipped": True, "reason": "not_found"}
            if not folder.schedule_enabled:
                return {"skipped": True, "reason": "disabled"}

            dao.update(
                folder_id,
                last_schedule_status="running",
                last_scheduled_at=datetime.now(),
            )

            stats = {
                "new_images": 0,
                "enqueued": 0,
                "skipped": 0,
                "pages_fetched": 0,
                "duration_sec": 0.0,
                "errors": [],
            }
            start = time.monotonic()

            try:
                raw_tags = (folder.tags or "").strip()
                if not raw_tags:
                    raise ValueError("folder has no tags configured")

                last_id: Optional[int] = folder.last_synced_id
                if last_id is None and folder.schedule_mode == "last_id":
                    with YandeDataRepository() as repo:
                        last_id = repo.get_max_id_for_tags(raw_tags)

                max_images = (
                    folder.schedule_max_images
                    if folder.schedule_max_images is not None
                    else config.scheduler.max_images_per_run_default
                )
                max_pages = config.scheduler.max_pages_per_run

                query_params_obj = FavoritesService._parse_tags_to_params(raw_tags)
                tags_for_api = (query_params_obj.tags or raw_tags) if query_params_obj else raw_tags

                yande_api = YandeApi()
                enqueued_count = 0
                page = 1
                stop = False
                processed_max_id: Optional[int] = None

                while page <= max_pages and enqueued_count < max_images:
                    try:
                        rank_params = YandeApi.PostRankQueryParams(
                            page=page, limit=100, tags=tags_for_api
                        )
                        page_data = await asyncio.to_thread(yande_api.get_ranking, rank_params)
                        items = page_data.root if page_data else []
                    except Exception as api_err:
                        stats["errors"].append(f"page {page} api error: {api_err}")
                        logger.exception(f"Folder {folder_id} page {page} failed")
                        raise

                    if not items:
                        break

                    for item in items:
                        if enqueued_count >= max_images:
                            stop = True
                            break

                        if last_id is not None and item.id <= last_id:
                            stop = True
                            break

                        stats["new_images"] += 1
                        if processed_max_id is None or item.id > processed_max_id:
                            processed_max_id = item.id
                        try:
                            with YandeDataRepository() as repo:
                                # TODO 查询优化，需要批量查询避免数据库连接数开销
                                existing = repo.get_by_id(item.id)
                                repo.upsert(item)
                                should_enqueue = existing is None or not existing.down_flag

                            if should_enqueue:
                                await DownloadService.create_task(item.id)
                                enqueued_count += 1
                                stats["enqueued"] += 1
                        except Exception as item_err:
                            stats["errors"].append(f"item {item.id} error: {item_err}")
                            logger.exception(f"Folder {folder_id} item {item.id} failed")
                            continue

                    if stop:
                        break
                    page += 1
                    # TODO 临时解决方案，后续多任务使用队列获取访问api防止并发导致api超限
                    time.sleep(10)

                stats["pages_fetched"] = page
                stats["duration_sec"] = round(time.monotonic() - start, 2)

                update_kwargs = {
                    "last_schedule_status": "success",
                    "last_schedule_stats": stats,
                }
                if processed_max_id is not None:
                    update_kwargs["last_synced_id"] = processed_max_id
                dao.update(folder_id, **update_kwargs)
                logger.info(
                    f"Folder {folder_id} schedule success: enqueued={stats['enqueued']} "
                    f"pages={stats['pages_fetched']} duration={stats['duration_sec']}s"
                    f" last_synced_id={update_kwargs.get('last_synced_id')}"
                )
                return stats

            except Exception as e:
                stats["errors"].append(str(e))
                stats["duration_sec"] = round(time.monotonic() - start, 2)
                dao.update(
                    folder_id,
                    last_schedule_status="failed",
                    last_schedule_stats=stats,
                )
                logger.exception(f"Folder {folder_id} schedule failed")
                return stats
