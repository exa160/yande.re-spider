from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from pydantic import BaseModel, ConfigDict

from src.api import APILoader
from src.common.constant import path_constant
from src.middleware.downloader import DownloadMiddleware
from src.middleware.errors import ErrorHandleMiddleware
from src.middleware.frontend_static import FrontendStaticLoader
from src.middleware.loggers import LoggerMiddleware
from src.middleware.session import RequestSessionMiddleware


class AppConfig(BaseModel):
    """FastAPI 应用配置"""
    model_config = ConfigDict(frozen=True)

    title: str = "Yande.re Local Picture Manager"
    description: str = "本地图片管理工具，提供图片查询、下载和管理功能"
    version: str = "1.0.2"
    docs_url: str = "/docs"
    redoc_url: str = "/redoc"


app_config = AppConfig()


def init_app(app: FastAPI) -> FastAPI:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    path_constant.originals_dir.mkdir(parents=True, exist_ok=True)
    path_constant.previews_dir.mkdir(parents=True, exist_ok=True)
    RequestSessionMiddleware.init_app(app)
    DownloadMiddleware.init_app(app)
    APILoader.init_app(app)
    LoggerMiddleware.init_app(app, path_constant.log_dir)
    ErrorHandleMiddleware.init_app(app)
    FrontendStaticLoader.init_app(app)

    logger.info("FastAPI application initialized successfully")

    return app
