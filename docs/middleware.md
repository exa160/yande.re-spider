# 中间件规范

## 目录结构

项目把"启动期需要的各种 hook"分成两类：

- `src/middleware/` — 真正的 ASGI/Starlette 中间件（session、errors、loggers、frontend_static）
- `src/lifecycle/` — 业务启动期钩子（lifespan 组合器、download、scheduler），类名后缀用 `Lifecycle`/`Registry`

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
    RequestSessionMiddleware.init_app(app)        # Session 管理
    APILoader.init_app(app)                       # 路由加载
    LoggerMiddleware.init_app(app, path_constant.log_dir)
    ErrorHandleMiddleware.init_app(app)           # 错误处理
    FrontendStaticLoader.init_app(app)            # 前端静态资源

    # 3. 启动期钩子（必须在所有 init_app 之后调用, 见下文）
    LifespanRegistry.register(DownloadLifecycle.lifespan)
    LifespanRegistry.register(SchedulerLifecycle.lifespan)
    LifespanRegistry.init_app(app)
```

## Lifespan 钩子规范

`LifespanRegistry` 解决 Starlette `app.router.lifespan_context` 是单值属性、多次赋值会互相覆盖的问题。

- **业务 Lifecycle 只暴露 `lifespan`**（`@staticmethod @asynccontextmanager`），不提供 `init_app`。
- **`LifespanRegistry.register(hook)`** 按启动顺序入栈。
- **`LifespanRegistry.init_app(app)`** 内部递归组合钩子并挂到 `app.router.lifespan_context`，**必须最后调用**。

启动顺序 = 注册顺序，关闭按 LIFO 触发。

## 自定义中间件模板

注意：项目统一用 **Pure ASGI middleware**（`__init__(self, app)` + `__call__(scope, receive, send)`）。
不要用 `starlette.middleware.base.BaseHTTPMiddleware`——后者内部用 `anyio.create_task_group` 把 endpoint 跑到新 task，导致 `ContextVar` 跨 task 不共享、DAO 的 INSERT 提交不到（zombie 事务）。

```python
from starlette.types import ASGIApp, Receive, Scope, Send
from fastapi import FastAPI


class MyASGIMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        # 前置处理
        await self.app(scope, receive, send)
        # 后置处理

    @staticmethod
    def init_app(app: FastAPI) -> None:
        app.add_middleware(MyASGIMiddleware)
```

## RequestSessionMiddleware（Session 管理）

```python
# src/middleware/session.py
from contextvars import ContextVar
from typing import Optional

from fastapi import FastAPI
from sqlalchemy.orm import Session
from starlette.types import ASGIApp, Receive, Scope, Send

from src.dao.database import _get_session_factory

_request_session: ContextVar[Optional[Session]] = ContextVar(
    "request_session", default=None
)


class RequestSessionMiddleware:
    """Pure ASGI middleware, 对外 API 兼容 init_app / get_session / remove_session"""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        session = _get_session_factory()()
        token = _request_session.set(session)
        try:
            # 同 task 直接 await -> ContextVar 正确传播
            await self.app(scope, receive, send)
            session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            _request_session.reset(token)
            session.close()

    @staticmethod
    def get_session() -> Session:
        session = _request_session.get()
        if session is None:
            raise RuntimeError(
                "RequestSessionMiddleware not active. "
                "DAO called outside HTTP request context, or "
                "ContextVar cross-task propagation regressed. "
                "For background tasks, use 'with FavoriteDao() as dao:'."
            )
        return session

    @staticmethod
    def init_app(app: FastAPI) -> None:
        app.add_middleware(RequestSessionMiddleware)

    @staticmethod
    def remove_session() -> None:
        _request_session.set(None)
```
