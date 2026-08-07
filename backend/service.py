import os
import sys

import uvicorn
from fastapi import FastAPI

from src import init_app, app_config, _resolve_paths

if "uvicorn" in sys.argv[0]:
    _resolve_paths()  # frozen 环境必须先解析路径
    main_app = FastAPI(**app_config.model_dump())
    init_app(main_app)


if __name__ == "__main__":
    _resolve_paths()
    main_app = FastAPI(docs_url="/docs", redoc_url="/redoc")
    main_app = init_app(main_app)
    host = os.environ.get("YANDE_HOST", "127.0.0.1")
    port = int(os.environ.get("YANDE_PORT", "0"))  # 0 = OS 自动分配
    uvicorn.run(main_app, host=host, port=port)
