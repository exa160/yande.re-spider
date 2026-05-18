from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from pydantic import BaseModel, ConfigDict

from src.api import APILoader
from src.common.constant import path_constant
from src.common.settings import config
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
    version: str = "1.0.6"
    docs_url: str = "/docs"
    redoc_url: str = "/redoc"


app_config = AppConfig()


def work_dir_setup():
    """工作目录设置，确保必要的目录存在"""
    for path in [path_constant.data_dir, path_constant.download_dir, path_constant.log_dir]:
        path.mkdir(parents=True, exist_ok=True)


def check_database_migration():
    """检查数据库迁移状态，若 Alembic 版本不一致则记录警告"""
    try:
        from alembic.config import Config as AlembicConfig
        from alembic.script import ScriptDirectory
        from alembic.runtime.migration import MigrationContext
        from src.dao.database import get_db_engine

        alembic_cfg = AlembicConfig()
        alembic_cfg.set_main_option("script_location", str(path_constant.base_dir / "migrations"))
        script = ScriptDirectory.from_config(alembic_cfg)
        engine = get_db_engine()
        with engine.connect() as conn:
            context = MigrationContext.configure(conn)
            current_rev = context.get_current_revision()
        head_rev = script.get_current_head()
        if current_rev != head_rev:
            logger.warning(
                f"Database migration outdated: current={current_rev}, head={head_rev}. "
                "Run 'alembic upgrade head' to apply pending migrations."
            )
    except Exception as e:
        logger.debug(f"Migration check skipped: {e}")


def init_app(app: FastAPI) -> FastAPI:
    if not config.cors.allow_origins:
        logger.warning("CORS allow_origins is empty, no cross-origin requests will be allowed")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors.allow_origins,
        allow_credentials=config.cors.allow_credentials,
        allow_methods=config.cors.allow_methods,
        allow_headers=config.cors.allow_headers,
    )
    work_dir_setup()
    check_database_migration()
    RequestSessionMiddleware.init_app(app)
    DownloadMiddleware.init_app(app)
    APILoader.init_app(app)
    LoggerMiddleware.init_app(app, path_constant.log_dir)
    ErrorHandleMiddleware.init_app(app)
    FrontendStaticLoader.init_app(app)

    logger.info("FastAPI application initialized successfully")

    return app
