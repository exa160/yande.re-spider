from fastapi import FastAPI
from loguru import logger
from starlette.responses import FileResponse, JSONResponse
from starlette.staticfiles import StaticFiles

from src import path_constant
from src.common.constant import ErrMsg
from src.middleware.errors import APIException
from src.models.response.base_response import BaseResponse


class FrontendStaticLoader:
    @staticmethod
    def init_app(app: FastAPI) -> None:
        frontend_dist = path_constant.frontend_dist
        if not frontend_dist.exists():
            logger.info(f"No frontend file found.")
            return

        logger.info(f"Frontend file load: {frontend_dist}")
        assets_dir = frontend_dist / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")
        app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="root")
        logger.info("WebServer application initialized for web server")

        # 健康检查接口
        @app.get("/health", tags=["系统"])
        async def health_check():
            return BaseResponse()

        # SPA fallback - 必须放在所有API路由注册之后
        @app.get("/{path:path}", include_in_schema=False)
        async def serve_spa(path: str):
            index_path = frontend_dist / "index.html"
            if index_path.exists():
                return FileResponse(index_path)
            raise APIException(ErrMsg.NOT_FOUND_ERROR)
