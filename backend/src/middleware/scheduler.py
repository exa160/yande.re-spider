from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from src.dao.favorite_dao import FavoriteDao
from src.infrastructure.scheduler import schedule_manager


class SchedulerMiddleware:
    @staticmethod
    def init_app(app: FastAPI):
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            schedule_manager.start()
            SchedulerMiddleware._reload_schedules()
            try:
                yield
            finally:
                schedule_manager.shutdown(wait=False)
                logger.info("Scheduler stopped")

        app.router.lifespan_context = lifespan

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
