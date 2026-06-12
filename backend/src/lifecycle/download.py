from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from src.infrastructure.download_queue import download_queue


class DownloadLifecycle:
    @staticmethod
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # 启动
        await download_queue.start(num_workers=5)
        logger.info("下载队列已启动")
        try:
            yield
        finally:
            # 关闭
            await download_queue.stop()
            logger.info("下载队列已停止")
