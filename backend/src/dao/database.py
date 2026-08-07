import os

from typing import Optional

from sqlalchemy import URL, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool, StaticPool

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
            pool_recycle=1800,
            pool_pre_ping=True,
            pool_use_lifo=True,
            pool_reset_on_return="rollback",
            connect_args={"connect_timeout": 10},
            echo=False,
            pool_size=10,
            max_overflow=20,
            pool_timeout=10,
        )
    else:
        _cached_engine = create_engine(
            f"sqlite:///{path_constant.sqlite_file}",
            connect_args={"timeout": 30, "check_same_thread": False},
            poolclass=NullPool,
        )
    # TODO 考虑取消自动建表/迁移，改为手动执行脚本
    Base.metadata.create_all(bind=_cached_engine)

    _auto_migrate(_cached_engine)

    return _cached_engine


def _auto_migrate(engine) -> None:
    from sqlalchemy import (
        Boolean, Column, DateTime, Integer, JSON, String, inspect
    )
    from sqlalchemy.schema import CreateColumn
    from loguru import logger

    inspector = inspect(engine)
    if "favorite_folders" not in inspector.get_table_names():
        return

    existing = {c["name"] for c in inspector.get_columns("favorite_folders")}

    desired = [
        Column("schedule_enabled", Boolean, nullable=False, server_default="0"),
        Column("schedule_cron", String(64), nullable=False, server_default=""),
        Column(
            "schedule_mode",
            String(16),
            nullable=False,
            server_default="last_id",
        ),
        Column("schedule_max_images", Integer, nullable=True),
        Column("last_scheduled_at", DateTime, nullable=True),
        Column("last_schedule_status", String(16), nullable=True),
        Column("last_schedule_stats", JSON, nullable=True),
        Column("last_synced_id", Integer, nullable=True),
    ]

    dialect = engine.dialect
    with engine.begin() as conn:
        for col in desired:
            if col.name in existing:
                continue
            ddl = str(CreateColumn(col).compile(dialect=dialect))
            try:
                conn.exec_driver_sql(
                    f"ALTER TABLE favorite_folders ADD COLUMN {ddl}"
                )
                logger.info(
                    f"Auto-migrate: ADD COLUMN favorite_folders.{col.name}"
                )
            except Exception as e:
                logger.warning(
                    f"Auto-migrate failed for {col.name}: {e}"
                )


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
    def __init__(self, session: Optional[Session] = None):
        self._session = session
        self.owns_session = session is None

    def __enter__(self):
        if self._session is None:
            self._session = _get_session_factory()()
            self.owns_session = True
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._session and self.owns_session:
            try:
                if exc_type is None:
                    self._session.commit()
                else:
                    self._session.rollback()
            finally:
                self._session.close()
                self._session = None       # 重置，防止下次复用已关闭的 session
                self.owns_session = False
        return False

    @property
    def session(self) -> Session:
        # 显式构造时优先 (with FavoriteDao(s) as dao:)
        if self._session is not None:
            return self._session
        # 单例路径: 每次从 ContextVar 拿当前请求 session
        # 禁止缓存! 缓存会导致下次请求拿到已 close 的旧 session
        # 请求外场景（后台调度/CLI）必须用 with DAO() as dao: 显式上下文
        from src.middleware.session import RequestSessionMiddleware
        return RequestSessionMiddleware.get_session()