from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from starlette.staticfiles import StaticFiles

from backend.src.api import APILoader
from backend.src.common.constant import path_constant
from backend.src.middleware.downloader import DownloadMiddleware
from backend.src.middleware.errors import ErrorHandleMiddleware
from backend.src.middleware.loggers import LoggerMiddleware


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
    frontend_dist = path_constant.frontend_dist
    if frontend_dist.exists():
        assets_dir = frontend_dist / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")
        app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="root")
        logger.info(f"frontend file load: {frontend_dist}")

    logger.info("Flask application initialized successfully")

    return app
