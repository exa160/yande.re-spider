import logging
import sys
from pathlib import Path

from fastapi import FastAPI
from loguru import logger


class InterceptHandler(logging.Handler):
    """将标准 logging 日志重定向到 loguru"""
    def emit(self, record):
        # 获取对应的 loguru 级别
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # 查找调用帧，使日志来源更准确
        frame, depth = logging.currentframe(), 2
        while frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


class LoggerMiddleware:
    @staticmethod
    def init_app(_: FastAPI, log_dir: str = "logs", log_level: str = "INFO"):
        """
        初始化 loguru 日志系统，支持应用日志和 uvicorn 日志分离

        Args:
            _: FastAPI 应用实例
            log_dir: 日志目录路径，默认为 logs
            log_level: 日志级别，默认为 INFO
        """
        # 创建日志目录
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)

        # 移除 loguru 默认的控制台 handler
        logger.remove()

        # 添加控制台输出（带颜色，格式清晰）
        logger.add(
            sys.stderr,
            format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
                   "<level>{level: <8}</level> | "
                   "<cyan>{name}</cyan>:"
                   "<cyan>{function}</cyan>:"
                   "<cyan>{line}</cyan> - "
                   "<level>{message}</level>",
            level=log_level,
            colorize=True,
        )

        # 应用日志文件（排除 uvicorn 相关日志）
        logger.add(
            log_path / "app.log",
            rotation="500 MB",
            retention="10 days",
            compression="zip",
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | "
                   "{level: <8} | {name}:{function}:{line} - {message}",
            level=log_level,
            enqueue=True,
            filter=lambda record: not record["name"].startswith("uvicorn")
        )

        # uvicorn 日志单独存放
        logger.add(
            log_path / "uvicorn.log",
            rotation="500 MB",
            retention="10 days",
            compression="zip",
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | "
                   "{level: <8} | {name}:{function}:{line} - {message}",
            level=log_level,
            enqueue=True,
            filter=lambda record: record["name"].startswith("uvicorn")
        )

        # 拦截标准 logging 日志
        logging.basicConfig(handlers=[InterceptHandler()], level=logging.INFO, force=True)

        # 设置 uvicorn 相关 logger 的处理器（确保被拦截）
        # for name in ["uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"]:
        #     logging.getLogger(name).handlers = [InterceptHandler()]
        #     # 禁止 propagate，避免重复输出
        #     logging.getLogger(name).propagate = False

        # 可选：降低第三方库的日志级别，减少噪音
        logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

        logger.info("Loguru initialized successfully")
