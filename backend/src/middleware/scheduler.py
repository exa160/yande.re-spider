from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger
from sqlalchemy import select

from src.dao.database import _get_session_factory
from src.infrastructure.scheduler import schedule_manager
from src.models.database.yande import FavoriteFolder


class SchedulerMiddleware:
    @staticmethod
    def init_app(app: FastAPI):
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            schedule_manager.start()
            try:
                session = _get_session_factory()()
                try:
                    folders = session.execute(
                        select(FavoriteFolder).where(FavoriteFolder.schedule_enabled == True)  # noqa: E712
                    ).scalars().all()
                    folder_dicts = [
                        {
                            "id": f.id,
                            "schedule_cron": f.schedule_cron,
                            "schedule_mode": f.schedule_mode,
                            "schedule_max_images": f.schedule_max_images,
                        }
                        for f in folders
                    ]
                    schedule_manager.reload_from_db(folder_dicts)
                    logger.info(f"Loaded {len(folder_dicts)} scheduled folders from DB")
                finally:
                    session.close()
            except Exception as e:
                logger.exception(f"Failed to reload schedules from DB: {e}")

            yield

            schedule_manager.shutdown(wait=False)
            logger.info("Scheduler stopped")

        app.router.lifespan_context = lifespan
