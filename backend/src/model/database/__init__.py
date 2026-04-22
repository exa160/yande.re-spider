"""
数据库连接池管理模块

提供：
- 引擎创建（支持 SQLite 和 MariaDB）
- 会话管理（上下文管理器）
- FastAPI 依赖注入
- 异常自动回滚
- 外部脚本调用支持

使用方式：

1. FastAPI 依赖注入:
   ```python
   from backend.src.model.database import get_db_session

   @app.get("/items")
   async def get_items(session: Session = Depends(get_db_session)):
       ...
   ```

2. 外部脚本调用（同步）:
   ```python
   from backend.src.model.database import DatabaseManager

   with DatabaseManager.get_session() as session:
       results = session.query(Model).all()
   ```

3. 异步上下文管理器:
   ```python
   from backend.src.model.database import AsyncSessionLocal

   async with AsyncSessionLocal() as session:
       results = await session.execute(select(Model))
   ```
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional

from backend.config.constant import DATA_DIR
from loguru import logger
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker, SessionTransaction
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session as SQLModelSession

from backend.config.settings import config


# ============================================================
# 引擎创建
# ============================================================


def _get_sqlite_url(db_path: Path) -> str:
    """构建 SQLite 数据库 URL"""
    return f"sqlite:///{db_path.as_posix()}"


def _get_mariadb_url() -> str:
    """构建 MariaDB 数据库 URL"""
    db_cfg = config.database
    return (
        f"mariadb+mariadbconnector://{db_cfg.user}:{db_cfg.password}@"
        f"{db_cfg.host}:{db_cfg.port}/{db_cfg.schema_name}?charset=utf8"
    )


def _get_engine() -> Engine:
    """
    创建数据库引擎（单例模式）

    根据配置选择 SQLite 或 MariaDB：
    - SQLite: 使用 StaticPool 保证线程安全，支持多线程访问
    - MariaDB: 使用连接池管理并发连接
    """
    use_mariadb = config.database.enable and config.database.host

    if use_mariadb:
        engine = create_engine(
            _get_mariadb_url(),
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            pool_recycle=3600,
            echo=False,
        )
        logger.info(
            f"MariaDB engine created: {config.database.host}:{config.database.port}/"
            f"{config.database.schema_name}"
        )
    else:
        db_dir = DATA_DIR
        db_dir.mkdir(parents=True, exist_ok=True)
        db_path = db_dir / "yande_data.db"
        engine = create_engine(
            _get_sqlite_url(db_path),
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            echo=False,
        )
        logger.info(f"SQLite engine created: {db_path.as_posix()}")

    return engine


# 全局引擎实例（延迟初始化）
_engine: Optional[Engine] = None


def get_engine() -> Engine:
    """获取全局数据库引擎（线程安全单例）"""
    global _engine
    if _engine is None:
        _engine = _get_engine()
    return _engine


def reset_engine() -> None:
    """重置引擎（用于测试或配置变更后重新初始化）"""
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None


# ============================================================
# 会话工厂
# ============================================================


_SessionLocal = None


def _get_session_factory() -> sessionmaker:
    """获取会话工厂（延迟初始化）"""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=get_engine(),
            expire_on_commit=False,
        )
    return _SessionLocal


def get_session_factory() -> sessionmaker:
    """获取会话工厂（公开接口）"""
    return _get_session_factory()


# ============================================================
# 会话上下文管理器
# ============================================================


class DatabaseSession:
    """
    数据库会话上下文管理器

    提供简化的会话管理，支持：
    - 自动提交/回滚
    - 异常自动回滚
    - 上下文管理器协议

    用法：
    ```python
    with DatabaseSession() as session:
        session.add(obj)
        # 自动 commit，异常时自动 rollback
    ```
    """

    def __init__(self, session: Optional[Session] = None):
        self._session = session
        self._owns_session = session is None

    def __enter__(self) -> Session:
        if self._session is None:
            self._session = _get_session_factory()()
        return self._session

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        if self._session is not None and self._owns_session:
            if exc_type is not None:
                logger.warning(f"Database session rollback: {exc_val}")
                self._session.rollback()
            else:
                try:
                    self._session.commit()
                except Exception as e:
                    logger.error(f"Database commit error: {e}")
                    self._session.rollback()
                    raise
            self._session.close()
        return False  # 不抑制异常


class DatabaseManager:
    """
    数据库管理器（静态方法集合）

    用于外部脚本调用，支持：
    - 同步会话获取
    - 上下文管理器
    - 表创建
    """

    @staticmethod
    @contextmanager
    def get_session() -> Generator[Session, None, None]:
        """
        获取数据库会话的上下文管理器（兼容旧代码）

        用法：
        ```python
        from backend.src.model.database import DatabaseManager

        with DatabaseManager.get_session() as session:
            results = session.query(Model).all()
        ```
        """
        session = _get_session_factory()()
        try:
            yield session
            session.commit()
        except Exception as e:
            logger.warning(f"Database operation failed, rolling back: {e}")
            session.rollback()
            raise
        finally:
            session.close()

    @staticmethod
    def create_all_tables() -> None:
        """创建所有表（基于 SQLModel.metadata）

        使用 checkfirst=True 避免重复创建已存在的表。
        如果表已存在，SQLAlchemy 会跳过而不是报错。
        """
        from backend.src.model.database.models import (  # noqa: F401
            YandeTag,
            YandeArtist,
            YandeData,
            FavoriteFolder,
            TagLocalStats,
        )

        # 使用 checkfirst=True 跳过已存在的表，避免重复定义错误
        SQLModel.metadata.create_all(bind=get_engine(), checkfirst=True)
        logger.info("Database tables created/verified")

    @staticmethod
    def drop_all_tables() -> None:
        """删除所有表（谨慎使用）"""
        SQLModel.metadata.drop_all(bind=get_engine())
        logger.warning("All database tables dropped")

    @staticmethod
    def get_engine() -> Engine:
        """获取数据库引擎"""
        return get_engine()

    @staticmethod
    def refresh_config() -> None:
        """刷新配置并重置引擎（配置变更后调用）"""
        reset_engine()


# ============================================================
# FastAPI 依赖注入
# ============================================================


def get_db_session() -> Generator[Session, None, None]:
    """
    FastAPI 依赖注入：获取数据库会话

    用法：
    ```python
    from fastapi import Depends

    @app.get("/items")
    async def get_items(session: Session = Depends(get_db_session)):
        results = session.query(Model).all()
        return results
    ```
    """
    session = _get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception as e:
        logger.warning(f"Database session error, rolling back: {e}")
        session.rollback()
        raise
    finally:
        session.close()


def get_db_session_dependency():
    """
    返回 FastAPI Depends 调用的快捷方式

    与 get_db_session 完全等价，提供更语义化的导入方式：
    ```python
    from backend.src.model.database import DatabaseSessionDep

    @app.get("/items")
    async def get_items(session: Session = DatabaseSessionDep):
        ...
    ```
    """
    return get_db_session


# 常用依赖注入快捷方式
DatabaseSessionDep = get_db_session


# ============================================================
# 初始化
# ============================================================


def init_database() -> None:
    """
    初始化数据库：创建引擎和所有表

    应用启动时调用一次：
    ```python
    from backend.src.model.database import init_database

    @app.on_event("startup")
    async def startup():
        init_database()
    ```
    """
    # 确保引擎已初始化
    engine = get_engine()

    # 创建所有表
    DatabaseManager.create_all_tables()

    logger.info("Database initialization complete")


# ============================================================
# 导出
# ============================================================

__all__ = [
    # 核心
    "get_engine",
    "reset_engine",
    "get_session_factory",
    "DatabaseManager",
    "DatabaseSession",
    # 依赖注入
    "get_db_session",
    "get_db_session_dependency",
    "DatabaseSessionDep",
    # 初始化
    "init_database",
    # SQLModel 基类（用于类型注解）
    "SQLModel",
    # 同步 Session（用于类型注解）
    "Session",
]
