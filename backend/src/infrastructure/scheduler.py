from __future__ import annotations

import asyncio
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger


class ScheduleManager:
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


async def _on_folder_trigger(folder_id: int) -> None:
    from src.services.favorite_scheduler import run_folder_schedule
    asyncio.create_task(run_folder_schedule(folder_id))


schedule_manager = ScheduleManager()
