import pytest
from sqlalchemy import (
    Boolean, Column, DateTime, Integer, JSON, String, create_engine, inspect
)
from sqlalchemy.schema import CreateColumn
from sqlalchemy.orm import sessionmaker

from src.dao.database import _auto_migrate
from src.models.database.yande import Base, FavoriteFolder


@pytest.fixture
def sqlite_engine_without_schedule_cols():
    eng = create_engine("sqlite:///:memory:")
    from sqlalchemy import text
    with eng.connect() as conn:
        conn.execute(text(
            "CREATE TABLE favorite_folders ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "name VARCHAR(50) NOT NULL,"
            "tags TEXT DEFAULT '',"
            "color VARCHAR(10) DEFAULT '#409EFF',"
            "icon VARCHAR(32) DEFAULT 'folder',"
            "sort_order INTEGER DEFAULT 0,"
            "local_count INTEGER DEFAULT 0,"
            "online_count INTEGER DEFAULT 0,"
            "last_refresh DATETIME,"
            "created_at DATETIME,"
            "updated_at DATETIME"
            ")"
        ))
        conn.commit()
    yield eng
    eng.dispose()


def test_auto_migrate_skips_when_table_missing():
    eng = create_engine("sqlite:///:memory:")
    _auto_migrate(eng)
    insp = inspect(eng)
    assert "favorite_folders" not in insp.get_table_names()
    eng.dispose()


def test_auto_migrate_adds_all_seven_columns_to_sqlite(sqlite_engine_without_schedule_cols):
    insp = inspect(sqlite_engine_without_schedule_cols)
    before = {c["name"] for c in insp.get_columns("favorite_folders")}
    assert "schedule_enabled" not in before
    assert "last_schedule_stats" not in before

    _auto_migrate(sqlite_engine_without_schedule_cols)

    insp = inspect(sqlite_engine_without_schedule_cols)
    after = {c["name"] for c in insp.get_columns("favorite_folders")}
    assert "schedule_enabled" in after
    assert "schedule_cron" in after
    assert "schedule_mode" in after
    assert "schedule_max_images" in after
    assert "last_scheduled_at" in after
    assert "last_schedule_status" in after
    assert "last_schedule_stats" in after


def test_auto_migrate_is_idempotent(sqlite_engine_without_schedule_cols):
    _auto_migrate(sqlite_engine_without_schedule_cols)
    insp = inspect(sqlite_engine_without_schedule_cols)
    cols_first = {c["name"] for c in insp.get_columns("favorite_folders")}

    _auto_migrate(sqlite_engine_without_schedule_cols)
    _auto_migrate(sqlite_engine_without_schedule_cols)

    insp = inspect(sqlite_engine_without_schedule_cols)
    cols_second = {c["name"] for c in insp.get_columns("favorite_folders")}
    assert cols_first == cols_second


def test_auto_migrate_uses_dialect_aware_ddl_for_mariadb():
    from sqlalchemy.dialects import mysql
    eng = create_engine("mysql+pymysql://")
    dialect = eng.dialect
    cols = [
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
    ]
    for col in cols:
        ddl = str(CreateColumn(col).compile(dialect=dialect))
        if col.name == "schedule_enabled":
            assert "BOOL" in ddl or "TINYINT" in ddl
        if col.name == "last_schedule_stats":
            assert "JSON" in ddl
    eng.dispose()


def test_auto_migrate_runs_against_a_mariadb_shaped_engine(monkeypatch):
    from sqlalchemy.dialects import mysql

    class _FakeMariadbEngine:
        dialect = mysql.dialect()

        def begin(self):
            return _FakeConn()

    class _FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def exec_driver_sql(self, sql):
            captured.append(sql)

    captured = []

    class _FakeInspector:
        def get_table_names(self):
            return ["favorite_folders"]

        def get_columns(self, table):
            assert table == "favorite_folders"
            return []

    monkeypatch.setattr("sqlalchemy.inspect", lambda eng: _FakeInspector())

    _auto_migrate(_FakeMariadbEngine())

    assert len(captured) == 7, f"expected 7 ALTER statements, got {len(captured)}: {captured}"
    for sql in captured:
        assert sql.startswith("ALTER TABLE favorite_folders ADD COLUMN")
        assert "schedule" in sql.lower()
    joined = "\n".join(captured)
    assert "BOOL" in joined or "TINYINT" in joined
    assert "JSON" in joined
