import inspect
import os
import importlib.util
import traceback
from pathlib import Path
from types import ModuleType
from typing import Optional

from fastapi import FastAPI, APIRouter
from loguru import logger

from backend.src.common.constant import RouterMap

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


class APILoader:
    def __init__(self):
        self.base_path = Path(__file__).resolve().parent

    @staticmethod
    def init_app(app: FastAPI) -> FastAPI:
        api_loader = APILoader()
        api_loader.init_api(app)
        return app

    @staticmethod
    def _get_router_directory(api_dir: Path) -> list[Path]:
        python_files: list[Path] = []
        folders = list(api_dir.glob("*/"))
        for folder_path in folders:
            if folder_path.name in API_BLACKLIST:
                continue
            logger.info("Find router version {}", folder_path.stem)
            python_files.extend(folder_path.rglob("*.py"))
        return python_files

    def registry_router_from_file(self, app: FastAPI, file_path) -> ModuleType:
        module_name = file_path.stem
        prefix = file_path.relative_to(self.base_path.parent).with_suffix('')

        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Load API failed: {file_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for router_name, obj in inspect.getmembers(module):
            if isinstance(obj, APIRouter):
                logger.info(f"Register router: {router_name} -> {str(prefix.as_posix())}")
                app.include_router(obj, prefix=f"/{str(prefix.as_posix())}", tags=RouterMap.get_tags(module_name))
        return module

    def init_api(self, app: FastAPI) -> None:
        logger.info("API registry start.")
        python_files = self._get_router_directory(self.base_path)
        for file_path in python_files:
            try:
                _ = self.registry_router_from_file(app, file_path)
            except Exception as e:
                logger.warning("Load router failed: {}", str(e))
                logger.warning(traceback.print_exc())

        logger.info("API registry finish.")
