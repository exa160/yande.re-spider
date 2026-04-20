"""
FastAPI 主应用入口
提供RESTful API接口供前端调用
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
import sys

# 配置日志
logger.remove()
logger.add(sys.stderr, level="INFO")
logger.add("logs/api.log", rotation="10 MB", retention="7 days", level="DEBUG")

# 创建FastAPI应用
app = FastAPI(
    title="Yande.re Spider API",
    description="yande.re图片爬虫下载器API接口",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 获取项目根目录
ROOT_DIR = Path(__file__).parent.parent
FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"

# 挂载前端静态资源
if FRONTEND_DIST.exists():
    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")
    logger.info(f"前端静态文件已托管: {FRONTEND_DIST}")


# 健康检查接口
@app.get("/health", tags=["系统"])
async def health_check():
    return {"status": "ok", "message": "API服务运行正常"}


# API 根路径
@app.get("/api", tags=["系统"])
async def root():
    return {
        "name": "Yande.re Spider API",
        "version": "2.0.0",
        "docs": "/docs",
        "redoc": "/redoc",
    }


from backend.api import init_api
from backend.infrastructure.download_queue import download_queue

init_api(app, prefix_base="/api/v1")
logger.info("API路由加载成功")


@app.on_event("startup")
async def startup_event():
    await download_queue.start(num_workers=5)
    logger.info("下载队列已启动")


@app.on_event("shutdown")
async def shutdown_event():
    await download_queue.stop()
    logger.info("下载队列已停止")


# SPA fallback - 必须放在所有API路由注册之后
@app.get("/{path:path}", include_in_schema=False)
async def serve_spa(path: str):
    index_path = FRONTEND_DIST / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return JSONResponse(status_code=404, content={"message": "Frontend not found"})


# 全局异常处理
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"全局异常: {exc}")
    return JSONResponse(
        status_code=500, content={"code": 500, "message": f"服务器内部错误: {str(exc)}"}
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
