from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from src.api import APILoader
from src.common.constant import path_constant
from src.middleware.downloader import DownloadMiddleware
from src.middleware.errors import ErrorHandleMiddleware
from src.middleware.frontend_static import FrontendStaticLoader
from src.middleware.loggers import LoggerMiddleware


def init_app(app: FastAPI) -> FastAPI:
    # 配置CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # 初始化中间件
    DownloadMiddleware.init_app(app)
    APILoader.init_app(app)
    LoggerMiddleware.init_app(app, path_constant.log_dir)
    ErrorHandleMiddleware.init_app(app)
    FrontendStaticLoader.init_app(app)

    logger.info("Flask application initialized successfully")

    return app
