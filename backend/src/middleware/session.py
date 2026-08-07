"""HTTP 请求级别的 SQLAlchemy session 上下文管理 (Pure ASGI middleware)

Pure ASGI 替代 BaseHTTPMiddleware: 后者内部用 anyio.create_task_group
把 endpoint 跑在新 task，ContextVar 跨 task 不共享 → DAO 静默 new session
→ dispatch commit 不到 endpoint 的 INSERT → 数据半开事务 (zombie)。
直接 await self.app() 时 endpoint 跟 dispatch 在同一 task，ContextVar 正常。
"""
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
    """Pure ASGI middleware，对外 API 兼容 init_app / get_session / remove_session"""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        session = _get_session_factory()()
        token = _request_session.set(session)
        try:
            # 直接 await (同 task) → ContextVar 正确传播
            await self.app(scope, receive, send)
            session.commit()
        except Exception:
            session.rollback()  # 同步方法，await None 会抛 TypeError
            raise
        finally:
            _request_session.reset(token)
            session.close()

    @staticmethod
    def get_session() -> Session:
        """严格模式: ContextVar 为 None 时立即报错，不再静默 new session

        修复前 fallback 会掩盖 ContextVar 跨 task 失效问题。
        改 Pure ASGI 后正常请求都拿到 session；None 只意味 lifespan/定时任务
        直接调 DAO (应该用 with FavoriteDao() as dao:) 或 cross-task 回归。
        """
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
        """注册到 FastAPI app (FastAPI.add_middleware 内部用 Middleware 包装)"""
        app.add_middleware(RequestSessionMiddleware)

    @staticmethod
    def remove_session() -> None:
        """清空 ContextVar (兼容保留，通常不需要)"""
        _request_session.set(None)
