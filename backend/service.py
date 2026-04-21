import sys

import uvicorn
from fastapi import FastAPI

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


if __name__ == '__main__':
    main_app = FastAPI(
        docs_url="/docs",
        redoc_url="/redoc",
    )
    main_app = init_app(main_app)
    uvicorn.run(main_app, host="0.0.0.0", port=8000)
