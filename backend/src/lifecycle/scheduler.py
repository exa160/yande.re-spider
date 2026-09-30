from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from src.dao.favorite_dao import FavoriteDao
from src.infrastructure.scheduler import schedule_manager


class SchedulerLifecycle:
    @staticmethod
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        schedule_manager.start()
        SchedulerLifecycle._reload_schedules()
        SchedulerLifecycle.reload_tag_cache_schedule()
        try:
            yield
        finally:
            schedule_manager.shutdown(wait=False)
            logger.info("Scheduler stopped")

    @staticmethod
    def reload_tag_cache_schedule() -> None:
        """按当前配置挂载/卸载标签缓存的定时增量刷新。

        幂等：每次调用先卸载再按开关决定是否注册，因此
        「启动时挂一次」与「改配置后重挂」共用这一个入口。
        """
        try:
            from src.common import config

            schedule_manager.unregister_tag_cache_refresh()
            tag_cache_cfg = config.tag_cache
            if not tag_cache_cfg.enable_daily_refresh:
                logger.info("Tag cache daily refresh disabled by config")
                return
            schedule_manager.register_tag_cache_refresh(
                cron=tag_cache_cfg.refresh_cron,
                batch_limit=tag_cache_cfg.batch_limit,
            )
        except ValueError as e:
            logger.warning(f"Tag cache refresh schedule not registered: {e}")
        except Exception as e:
            logger.exception(f"Failed to register tag cache refresh schedule: {e}")

    @staticmethod
    def _reload_schedules() -> None:
        """从 DB 加载所有启用调度的收藏夹，注册到 APScheduler。"""
        try:
            with FavoriteDao() as dao:
                folders = dao.get_scheduled_folders()
                folder_dicts = [
                    {
                        "id": f.id,
                        "schedule_cron": f.schedule_cron,
                        "schedule_mode": f.schedule_mode,
                        "schedule_max_images": f.schedule_max_images,
                    }
                    for f in folders
                ]
        except Exception as e:
            logger.exception(f"Failed to reload schedules from DB: {e}")
            return

        schedule_manager.reload_from_db(folder_dicts)
        logger.info(f"Loaded {len(folder_dicts)} scheduled folders from DB")
