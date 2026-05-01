from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from src.api import APILoader
from src.common.constant import path_constant
from src.middleware.downloader import DownloadMiddleware
from src.middleware.errors import ErrorHandleMiddleware
from src.middleware.frontend_static import FrontendStaticLoader
from src.middleware.loggers import LoggerMiddleware
from src.middleware.session import RequestSessionMiddleware


def init_app(app: FastAPI) -> FastAPI:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    RequestSessionMiddleware.init_app(app)
    DownloadMiddleware.init_app(app)
    APILoader.init_app(app)
    LoggerMiddleware.init_app(app, path_constant.log_dir)
    ErrorHandleMiddleware.init_app(app)
    FrontendStaticLoader.init_app(app)

    logger.info("FastAPI application initialized successfully")

    return app
