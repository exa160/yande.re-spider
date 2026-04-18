import sys

import uvicorn
from fastapi import FastAPI
from loguru import logger

from src import init_app


if 'uvicorn' in sys.argv[0]:
    main_app = FastAPI(
        title="Yande.re Local Picture Manager",
        description="yande.re图片爬虫下载器API接口",
        version="2.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )
    init_app(main_app)

    # 健康检查接口
    @main_app.get("/health", tags=["系统"])
    async def health_check():
        return {"status": "ok", "message": "API服务运行正常"}
    
    # SPA fallback - 必须放在所有API路由注册之后
    # @main_app.get("/{path:path}", include_in_schema=False)
    # async def serve_spa(path: str):
    #     index_path = FRONTEND_DIST / "index.html"
    #     if index_path.exists():
    #         return FileResponse(index_path)
    #     return JSONResponse(status_code=404, content={"message": "Frontend not found"})
    logger.info("WebServer application initialized for web server")


if __name__ == '__main__':
    main_app = FastAPI(
        docs_url="/docs",
        redoc_url="/redoc",
    )
    main_app = init_app(main_app)
    uvicorn.run(main_app, host="0.0.0.0", port=8000)