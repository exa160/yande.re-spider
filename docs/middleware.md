# 中间件规范

## 中间件注册顺序

在 `backend/src/__init__.py` 的 `init_app()` 中按顺序注册：

```python
def init_app(app: FastAPI) -> FastAPI:
    # 1. CORS（FastAPI 内置）
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 2. 自定义中间件（按依赖顺序）
    app.add_middleware(RequestSessionMiddleware)  # Session 管理
    DownloadMiddleware.init_app(app)             # 下载相关
    APILoader.init_app(app)                       # 路由加载
    LoggerMiddleware.init_app(app, path_constant.log_dir)
    ErrorHandleMiddleware.init_app(app)          # 错误处理（最后注册）

    # ...
```

## 自定义中间件模板

```python
from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware


class MyCustomMiddleware(BaseHTTPMiddleware):
    @staticmethod
    async def dispatch(request: Request, call_next):
        # 前置处理
        response = await call_next(request)
        # 后置处理
        return response

    @classmethod
    def init_app(cls, app: FastAPI):
        app.add_middleware(cls)
```

## RequestSessionMiddleware（Session 管理）

```python
# src/middleware/session.py
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from contextvars import ContextVar
from sqlalchemy.orm import Session
from typing import Optional

from src.dao.database import get_db_engine, _get_session_factory

_request_session: ContextVar[Optional[Session]] = ContextVar("request_session", default=None)


class RequestSessionMiddleware(BaseHTTPMiddleware):
    @staticmethod
    def get_session() -> Session:
        session = _request_session.get()
        if session is None:
            session = _get_session_factory()()
            _request_session.set(session)
        return session

    async def dispatch(self, request: Request, call_next):
        session = _get_session_factory()()
        _request_session.set(session)

        try:
            response = await call_next(request)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
            _request_session.set(None)

        return response
```