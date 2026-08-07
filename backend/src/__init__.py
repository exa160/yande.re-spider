import shutil
import subprocess
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from pydantic import BaseModel, ConfigDict

from src.api import APILoader
from src.common.constant import _resolve_paths, path_constant
from src.lifecycle.download import DownloadLifecycle
from src.lifecycle.lifespan import LifespanRegistry
from src.lifecycle.scheduler import SchedulerLifecycle
from src.middleware.errors import ErrorHandleMiddleware
from src.middleware.frontend_static import FrontendStaticLoader
from src.middleware.loggers import LoggerMiddleware
from src.middleware.session import RequestSessionMiddleware


class AppConfig(BaseModel):
    """FastAPI 应用配置"""
    model_config = ConfigDict(frozen=True)

    title: str = "Yande.re Local Picture Manager"
    description: str = "本地图片管理工具，提供图片查询、下载和管理功能"
    version: str = "1.1.10"
    docs_url: str = "/docs"
    redoc_url: str = "/redoc"


app_config = AppConfig()


def _get_git_sha() -> str:
    """获取当前 git commit short SHA。

    优先级：
    1. frozen 环境：读取 sys._MEIPASS/version.txt（PyInstaller NSIS 打包时注入）
    2. 开发模式：subprocess 调用 git rev-parse
    3. 都不可用：返回 "unknown"
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        version_txt = Path(sys._MEIPASS) / "version.txt"
        if version_txt.exists():
            return version_txt.read_text(encoding="utf-8").strip() or "unknown"
    if not shutil.which("git"):
        return "unknown"
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def _print_startup_banner(config: AppConfig) -> None:
    """打印启动 banner: 版本号 + git SHA + 关键中间件 + 路径"""
    git_sha = _get_git_sha()
    py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    logger.info("=" * 66)
    logger.info(f"  {config.title} v{config.version} (git-{git_sha})")
    logger.info(f"  Python {py_version}")
    logger.info("-" * 66)
    logger.info(f"  Data dir   : {path_constant.data_dir}")
    logger.info(f"  Download   : {path_constant.download_dir}")
    logger.info(f"  Log dir    : {path_constant.log_dir}")
    logger.info(f"  Config     : {path_constant.config_file}")
    logger.info(f"  Docs       : {config.docs_url}  |  ReDoc: {config.redoc_url}")
    logger.info("=" * 66)


def work_dir_setup():
    """工作目录设置，确保必要的目录存在"""
    for path in [path_constant.data_dir, path_constant.download_dir, path_constant.log_dir]:
        path.mkdir(parents=True, exist_ok=True)


def init_app(app: FastAPI) -> FastAPI:
    _resolve_paths()  # 必须在任何中间件读 path_constant 之前
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    work_dir_setup()
    RequestSessionMiddleware.init_app(app)
    APILoader.init_app(app)
    LoggerMiddleware.init_app(app, path_constant.log_dir)
    ErrorHandleMiddleware.init_app(app)
    FrontendStaticLoader.init_app(app)
    LifespanRegistry.register(DownloadLifecycle.lifespan)
    LifespanRegistry.register(SchedulerLifecycle.lifespan)
    LifespanRegistry.init_app(app)

    _print_startup_banner(app_config)

    return app
