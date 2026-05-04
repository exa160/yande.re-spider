import os

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.common import config
from src.models.database.yande import Base

_cached_engine = None
_cached_session_factory = None


def get_db_engine():
    global _cached_engine

    if _cached_engine is not None:
        return _cached_engine

    use_mariadb = config.database.enable and config.database.host

    if use_mariadb:
        _cached_engine = create_engine(
            f"mariadb+mariadbconnector://{config.database.user}:{config.database.password.get_secret_value()}@"
            f"{config.database.host}:{config.database.port}/{config.database.schema_name}"
        )
    else:
        db_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "data",
            "yande_data.db",
        )
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        _cached_engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"timeout": 30, "check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=_cached_engine)

    return _cached_engine


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