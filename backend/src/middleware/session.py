from fastapi import FastAPI
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

    @staticmethod
    def init_app(app: FastAPI):
        app.add_middleware(RequestSessionMiddleware)

    @staticmethod
    def remove_session() -> None:
        _request_session.set(None)

    async def dispatch(self, request: Request, call_next):
        response = None
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
