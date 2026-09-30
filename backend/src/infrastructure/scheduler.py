from __future__ import annotations

import asyncio
from typing import Any, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger


class ScheduleManager:
    # 标签缓存定时刷新的固定 job id（非 folder_* 命名空间，与收藏夹调度区分）
    TAG_CACHE_JOB_ID = "tag_cache_daily_refresh"

    def __init__(self) -> None:
        self._scheduler: Optional[AsyncIOScheduler] = None
        self._job_folder_map: dict[str, int] = {}

    def _get_scheduler(self) -> AsyncIOScheduler:
        if self._scheduler is None:
            self._scheduler = AsyncIOScheduler()
        return self._scheduler

    def start(self) -> None:
        scheduler = self._get_scheduler()
        if not scheduler.running:
            scheduler.start()
            logger.info("ScheduleManager started")

    def shutdown(self, wait: bool = False) -> None:
        if self._scheduler is not None and self._scheduler.running:
            self._scheduler.shutdown(wait=wait)
            logger.info("ScheduleManager stopped")
        self._job_folder_map.clear()

    def register_folder(
        self,
        folder_id: int,
        cron: str,
        mode: str = "last_id",
        max_images: Optional[int] = None,
    ) -> None:
        if not cron or not cron.strip():
            raise ValueError("cron expression cannot be empty")
        if mode not in ("last_id", "max"):
            raise ValueError(f"mode must be 'last_id' or 'max', got: {mode}")

        job_id = f"folder_{folder_id}"
        scheduler = self._get_scheduler()

        try:
            trigger = CronTrigger.from_crontab(cron)
        except Exception as e:
            raise ValueError(f"Invalid cron expression '{cron}': {e}") from e

        scheduler.add_job(
            _on_folder_trigger,
            trigger=trigger,
            args=[folder_id],
            id=job_id,
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=300,
        )
        self._job_folder_map[job_id] = folder_id
        logger.info(f"Schedule registered: folder={folder_id} cron='{cron}' mode={mode} max_images={max_images}")

    def unregister_folder(self, folder_id: int) -> bool:
        job_id = f"folder_{folder_id}"
        scheduler = self._get_scheduler()
        try:
            scheduler.remove_job(job_id)
            self._job_folder_map.pop(job_id, None)
            logger.info(f"Schedule unregistered: folder={folder_id}")
            return True
        except Exception:
            return False

    def get_all_jobs(self) -> list[dict]:
        scheduler = self._get_scheduler()
        jobs = []
        for job in scheduler.get_jobs():
            next_run = job.next_run if hasattr(job, "next_run") else None
            jobs.append({
                "job_id": job.id,
                "folder_id": self._job_folder_map.get(job.id),
                "next_run_time": str(next_run) if next_run else None,
                "trigger": str(job.trigger),
            })
        return jobs

    def reload_from_db(self, folders: list[dict]) -> None:
        for f in folders:
            try:
                self.register_folder(
                    folder_id=f["id"],
                    cron=f["schedule_cron"],
                    mode=f.get("schedule_mode", "last_id"),
                    max_images=f.get("schedule_max_images"),
                )
            except ValueError as e:
                logger.warning(f"Skip schedule registration for folder {f['id']}: {e}")

    @staticmethod
    def _remove_job_everywhere(scheduler, job_id: str) -> bool:
        """把 job 从 jobstore 与 _pending_jobs 两处都摘掉。

        APScheduler 在 scheduler 尚未 ``start()`` 时会把 add_job 放进
        ``_pending_jobs``，而 ``remove_job()`` 只查 jobstore → 抛 JobLookupError。
        若忽略这点，重复注册会留下两个同 id 的 job（到点跑两遍）。
        私有属性访问做了 getattr 兜底，APScheduler 换版本时最多退化为
        「和以前一样只清 jobstore」，不会炸。
        """
        removed = False
        try:
            scheduler.remove_job(job_id)
            removed = True
        except Exception:
            pass
        pending = getattr(scheduler, "_pending_jobs", None)
        if pending is not None:
            try:
                kept = [j for j in pending if getattr(j, "id", None) != job_id]
                removed = removed or len(kept) != len(pending)
                pending[:] = kept
            except Exception:
                pass
        return removed

    def register_tag_cache_refresh(self, cron: str, batch_limit: int = 100) -> None:
        """注册标签缓存的定时增量刷新（单个全局 job，非每收藏夹）

        与 ``register_folder`` 分开：标签缓存是全局单表，一天一次足够，
        不需要按收藏夹注册。

        Raises:
            ValueError: cron 非法或 batch_limit 越界
        """
        if not cron or not cron.strip():
            raise ValueError("cron expression cannot be empty")
        if not isinstance(batch_limit, int) or batch_limit < 1:
            raise ValueError(f"batch_limit must be a positive int, got: {batch_limit}")

        scheduler = self._get_scheduler()
        try:
            trigger = CronTrigger.from_crontab(cron.strip())
        except Exception as e:
            raise ValueError(f"Invalid cron expression '{cron}': {e}") from e

        # 先显式摘干净再添加：replace_existing 在未 start() 的 scheduler 上不生效
        self._remove_job_everywhere(scheduler, self.TAG_CACHE_JOB_ID)

        scheduler.add_job(
            _on_tag_cache_trigger,
            trigger=trigger,
            args=[batch_limit],
            id=self.TAG_CACHE_JOB_ID,
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=3600,
        )
        logger.info(f"Tag cache refresh scheduled: cron='{cron}' batch_limit={batch_limit}")

    def unregister_tag_cache_refresh(self) -> bool:
        """移除标签缓存定时刷新 job（开关关闭 / 关停时调用）"""
        return self._remove_job_everywhere(self._get_scheduler(), self.TAG_CACHE_JOB_ID)

    def has_tag_cache_refresh(self) -> bool:
        scheduler = self._get_scheduler()
        return any(job.id == self.TAG_CACHE_JOB_ID for job in scheduler.get_jobs())


async def _on_folder_trigger(folder_id: int) -> None:
    """定时触发入口：防御性检查 + 顺手清理残留 job

    若 DB 中 folder 已不存在或 schedule_enabled=False，
    跳过本次触发并调用 unregister_folder 清理 APScheduler 中可能残留的 job。

    实现：DAO 调用必须用 with 显式上下文（无请求 ContextVar），
    整体通过 asyncio.to_thread 调度避免冻事件循环。
    """
    from src.services.favorite_scheduler import run_folder_schedule
    from src.dao.favorite_dao import FavoriteDao

    def _load_and_check() -> Optional[Any]:
        with FavoriteDao() as dao:
            folder = dao.get_by_id(folder_id)
            if not folder:
                return None
            return {
                "id": folder.id,
                "schedule_enabled": folder.schedule_enabled,
            }

    loaded = await asyncio.to_thread(_load_and_check)
    if loaded is None:
        logger.warning(
            f"Scheduled trigger skipped: folder {folder_id} not found, cleanup residual job"
        )
        schedule_manager.unregister_folder(folder_id)
        return
    if not loaded["schedule_enabled"]:
        logger.info(
            f"Scheduled trigger skipped: folder {folder_id} schedule disabled, cleanup residual job"
        )
        schedule_manager.unregister_folder(folder_id)
        return

    asyncio.create_task(run_folder_schedule(folder_id))


async def _on_tag_cache_trigger(batch_limit: int) -> None:
    """标签缓存定时刷新入口

    行为：走 ``TagCacheService.refresh_tags`` 的**增量**分支（表空时它自己转全量）。
    全程 to_thread：yande_api 是同步 requests，不解阻塞会卡住事件循环
    （此时下载进度上报 / 前端轮询全被拖住）。

    开关在触发时再判一次：配置可能在 job 注册后被改掉（如通过 PUT /config/tag-cache
    关闭），残留 job 顺带清理掉。
    """
    from src.services.tag_cache import TagCacheService

    try:
        from src.common import config

        if not config.tag_cache.enable_daily_refresh:
            logger.info("Tag cache refresh skipped: disabled by config, cleaning job")
            schedule_manager.unregister_tag_cache_refresh()
            return
    except Exception as e:
        logger.warning(f"Tag cache refresh skipped: cannot read config ({e})")
        return

    try:
        result = await asyncio.to_thread(TagCacheService.refresh_tags, batch_limit, False)
        logger.info(f"Tag cache refreshed by schedule: {result}")
    except Exception as e:
        logger.error(f"Scheduled tag cache refresh failed: {e}")


schedule_manager = ScheduleManager()
