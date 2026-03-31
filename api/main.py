"""
FastAPI 主应用入口
提供RESTful API接口供前端调用
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
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
    allow_origins=["*"],  # 生产环境应配置具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 健康检查接口
@app.get("/health", tags=["系统"])
async def health_check():
    """健康检查接口"""
    return {"status": "ok", "message": "API服务运行正常"}


# 根路径
@app.get("/", tags=["系统"])
async def root():
    """根路径"""
    return {
        "name": "Yande.re Spider API",
        "version": "2.0.0",
        "docs": "/docs",
        "redoc": "/redoc",
    }


try:
    from backend.api.routers import query, download, gallery, config

    app.include_router(query.router, prefix="/api/v1/query", tags=["查询"])
    app.include_router(download.router, prefix="/api/v1/download", tags=["下载"])
    app.include_router(gallery.router, prefix="/api/v1/gallery", tags=["图库"])
    app.include_router(config.router, prefix="/api/v1/config", tags=["配置"])
    logger.info("API路由加载成功")
except ImportError as e:
    logger.warning(f"部分路由模块未找到: {e}")


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
