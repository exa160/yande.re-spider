"""SQLite WAL 开启 + 旧数据不受影响。

WAL 只是改变日志/并发模式，journal_mode 会写入 DB 文件头；
不重写、不迁移任何业务表数据。本测试先在默认模式下写入旧数据，
再应用 WAL，确认模式生效且旧数据可读。
"""
from sqlalchemy import create_engine, text

from src.dao.database import _apply_sqlite_pragmas


def test_wal_mode_enabled_and_existing_data_intact(tmp_path):
    db_path = tmp_path / "wal.db"

    # 1. 默认 journal 模式下写入「旧数据」
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)"))
        conn.execute(text("INSERT INTO t (id, v) VALUES (1, 'old')"))
    engine.dispose()

    # 2. 模拟应用启动：重新打开并应用 WAL
    engine = create_engine(f"sqlite:///{db_path}")
    _apply_sqlite_pragmas(engine)
    with engine.connect() as conn:
        mode = conn.execute(text("PRAGMA journal_mode")).scalar()
        value = conn.execute(text("SELECT v FROM t WHERE id = 1")).scalar()
    engine.dispose()

    assert str(mode).lower() == "wal"
    assert value == "old"


def test_wal_is_persistent_across_reopen(tmp_path):
    """journal_mode 写在文件头：第二次打开即使不重新应用 pragma 仍是 WAL。"""
    db_path = tmp_path / "wal_persist.db"

    engine = create_engine(f"sqlite:///{db_path}")
    _apply_sqlite_pragmas(engine)
    with engine.connect() as conn:
        assert str(conn.execute(text("PRAGMA journal_mode")).scalar()).lower() == "wal"
    engine.dispose()

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        mode = conn.execute(text("PRAGMA journal_mode")).scalar()
    engine.dispose()

    assert str(mode).lower() == "wal"


def test_engine_uses_queue_pool_for_sqlite():
    """SQLite 必须用多连接池（StaticPool 单连接会让 to_thread 并发 session 互相踩状态）。"""
    import pytest

    from src.common import config

    if config.database.enable and config.database.host:
        pytest.skip("MariaDB mode")

    from src.dao.database import get_db_engine

    engine = get_db_engine()
    assert type(engine.pool).__name__ == "QueuePool"
