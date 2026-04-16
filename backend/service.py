import sys

import uvicorn
from fastapi import FastAPI
from loguru import logger

from src import init_app



if 'uvicorn' in sys.argv[0]:
    app = FastAPI(
        title="Yande.re Local Picture Manager",
        description="yande.re图片爬虫下载器API接口",
        version="2.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )
    app.setup()
    main_app = init_app(app)

    logger.info("WebServer application initialized for web server")



if __name__ == '__main__':
    app = FastAPI(
        docs_url="/docs",
        redoc_url="/redoc",
    )
    uvicorn.run(app, host="0.0.0.0", port=8000)