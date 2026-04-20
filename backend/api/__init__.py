"""
动态API加载模块

通过深度遍历 api 目录下的所有文件，自动发现并加载 APIRouter 实例。
支持黑名单机制，可以排除不需要加载的文件夹。
"""

import os
import importlib
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, APIRouter
from loguru import logger


API_BLACKLIST: set[str] = {
    "__pycache__",
    ".git",
    ".vscode",
    "node_modules",
    ".venv",
    "venv",
    "env",
    "dist",
    "build",
    ".egg-info",
    "__pypackages__",
}


def _get_api_dir() -> Path:
    return Path(__file__).resolve().parent


def _walk_api_directory(api_dir: Path) -> list[Path]:
    python_files: list[Path] = []

    for root, dirs, files in os.walk(api_dir, topdown=True):
        root_path = Path(root)
        dirs[:] = [d for d in dirs if d not in API_BLACKLIST]

        for file in files:
            if file.endswith(".py") and file != "__init__.py":
                python_files.append(root_path / file)

    return python_files


def _import_router_from_file(file_path: Path) -> Optional[APIRouter]:
    try:
        api_dir = _get_api_dir()
        relative_path = file_path.relative_to(api_dir.parent)
        module_parts = list(relative_path.parts)

        # backend/api/routers/query.py -> backend.api.routers.query
        module_parts[-1] = module_parts[-1][:-3]
        module_parts = [api_dir.parent.name] + module_parts
        module_name = ".".join(module_parts)

        module = importlib.import_module(module_name)
        router = getattr(module, "router", None)

        if isinstance(router, APIRouter):
            logger.debug(f"成功加载路由: {module_name}.router")
            return router

        return None

    except Exception as e:
        logger.warning(f"加载路由文件失败 {file_path}: {e}")
        return None


def init_api(
    app: FastAPI, api_dir: Optional[Path] = None, prefix_base: str = ""
) -> None:
    if api_dir is None:
        api_dir = _get_api_dir()

    logger.info(f"开始扫描 API 路由目录: {api_dir}")

    python_files = _walk_api_directory(api_dir)

    for file_path in python_files:
        router = _import_router_from_file(file_path)
        if router:
            router_name = file_path.stem
            prefix = (
                f"{prefix_base}/{router_name}" if prefix_base else f"/{router_name}"
            )
            app.include_router(router, prefix=prefix)
            logger.info(f"注册路由: {router_name} -> {prefix}")

    logger.info("API 路由注册完成")
