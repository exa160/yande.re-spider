import os

from sqlalchemy import URL, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.common import config
from src.common.constant import path_constant
from src.models.database.yande import Base

_cached_engine = None
_cached_session_factory = None


def get_db_engine():
    global _cached_engine

    if _cached_engine is not None:
        return _cached_engine

    use_mariadb = config.database.enable and config.database.host

    if use_mariadb:
        url = URL.create(
            drivername="mariadb+mariadbconnector",
            username=config.database.user,
            password=config.database.password.get_secret_value(),
            host=config.database.host,
            port=config.database.port,
            database=config.database.schema_name
        )
        _cached_engine = create_engine(url,
            pool_recycle=3600,          # 每小时回收连接
            pool_pre_ping=True,         # 自动重连
            echo=False,                 # 生产关闭 SQL 日志
            pool_size=10,              # 连接池大小
            max_overflow=20,           # 连接池溢出时最大创建的连接数
            pool_timeout=30,           # 获取连接的超时时间
        )
    else:
        _cached_engine = create_engine(
            f"sqlite:///{path_constant.sqlite_file}",
            connect_args={"timeout": 30, "check_same_thread": False},
            poolclass=StaticPool,
        )
    # TODO 考虑取消自动建表/迁移，改为手动执行脚本
    Base.metadata.create_all(bind=_cached_engine)

    return _cached_engine


def engine_change_handler():
    global _cached_session_factory
    global _cached_engine
    _cached_session_factory = None
    _cached_engine = None
    get_db_engine()


def _get_session_factory():
    global _cached_session_factory

    if _cached_session_factory is not None:
        return _cached_session_factory

    engine = get_db_engine()
    _cached_session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    return _cached_session_factory


class BaseDAO:
    def __init__(self, session: Session = None):
        self._session = session

    def __enter__(self):
        if self._session is None:
            self._session = _get_session_factory()()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._session:
            if exc_type is None:
                self._session.commit()
            else:
                self._session.rollback()
            self._session.close()
        return False

    @property
    def session(self) -> Session:
        if self._session is None:
            try:
                from src.middleware.session import RequestSessionMiddleware
                self._session = RequestSessionMiddleware.get_session()
            except Exception:
                self._session = _get_session_factory()()
        return self._session