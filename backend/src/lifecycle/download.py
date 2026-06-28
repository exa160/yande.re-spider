from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from src.common.constant import TaskStatus
from src.infrastructure.download_queue import download_queue, task_store


class DownloadLifecycle:
    @staticmethod
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # 启动：先从 DB 恢复活跃任务（含崩溃恢复），再启动队列
        recovered = task_store.load_from_db()

        pending_ids = task_store.get_pending_task_ids()
        for tid in pending_ids:
            await download_queue.add_task(tid)

        await download_queue.start(num_workers=5)
        logger.info(
            f"下载队列已启动（从 DB 恢复 {recovered} 个任务，"
            f"加入队列 {len(pending_ids)} 个 pending）"
        )
        try:
            yield
        finally:
            # 关闭
            await download_queue.stop()
            logger.info("下载队列已停止")
