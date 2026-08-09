import sys
from pathlib import Path

from fastapi import FastAPI
from loguru import logger
from starlette.responses import FileResponse
from starlette.staticfiles import StaticFiles

from src import path_constant
from src.common.constant import ErrMsg
from src.middleware.errors import APIException
from src.models.response.base_response import BaseResponse


def resolve_frontend_dist() -> Path:
    """解析前端 dist 路径。

    - frozen: sys._MEIPASS/frontend/dist（PyInstaller NSIS 打包位于 _internal/frontend/dist）
    - dev: path_constant.frontend_dist（仓库 frontend/dist）
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "frontend" / "dist"
    return path_constant.frontend_dist


class FrontendStaticLoader:
    @staticmethod
    def init_app(app: FastAPI) -> None:
        frontend_dist = resolve_frontend_dist()
        if not frontend_dist.exists():
            logger.info(f"No frontend file found at {frontend_dist}.")
            return

        logger.info(f"Frontend file load: {frontend_dist}")
        assets_dir = frontend_dist / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")
        app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="root")
        logger.info("WebServer application initialized for web server")

        @app.get("/health", tags=["系统"])
        async def health_check():
            return BaseResponse()

        @app.get("/{path:path}", include_in_schema=False)
        async def serve_spa(path: str):
            index_path = frontend_dist / "index.html"
            if index_path.exists():
                return FileResponse(index_path)
            raise APIException(ErrMsg.NOT_FOUND_ERROR)
