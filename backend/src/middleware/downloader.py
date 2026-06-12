from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from src.infrastructure.download_queue import download_queue, task_store


class DownloadMiddleware:
    @staticmethod
    def init_app(app: FastAPI):
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            # 启动：先从 DB 恢复活跃任务（含崩溃恢复），再启动队列
            recovered = task_store.load_from_db()
            await download_queue.start(num_workers=5)
            logger.info(f"下载队列已启动（从 DB 恢复 {recovered} 个任务）")
            try:
                yield
            finally:
                # 关闭
                await download_queue.stop()
                logger.info("下载队列已停止")

        app.router.lifespan_context = lifespan
