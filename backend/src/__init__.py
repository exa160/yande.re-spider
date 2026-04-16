from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger


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
    LoggerMiddleware.init_app(app)
    RequestIDMiddleware.init_app(app)
    ErrorHandlerMiddleware.init_app(app)

    # 初始化Celery（如果启用）
    if config.celery and config.celery.broker_url:
        from src.celery_task import init_celery_app
        init_celery_app(app)

    # 注册蓝图
    from src.api.v1 import api_v1
    app.register_blueprint(api_v1, url_prefix='/api/v1')

    logger.info("Flask application initialized successfully")

    return app
