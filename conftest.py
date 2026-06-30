"""pytest 全局配置 + 数据保护 fixture

历史背景：feature 分支的缩略图清理测试（test_gallery_cleanup.py 等）
和 DAO 测试用 `query(YandeData).delete()` 清空 yande_data 表后插入 fixture 数据，
但没有 teardown 恢复，导致真实数据被测试覆盖丢失（commit f93fc04 诊断报告）。

本 conftest.py 提供 autouse fixture，在每个测试前后自动保存/恢复 yande_data 表，
即使测试抛异常或被 SIGINT 中断也能保证数据安全。

实现细节：用 sqlite3 原生连接直接 DELETE+INSERT（绕过 SQLAlchemy ORM 类型检查，
否则 datetime 字段需要从字符串转回 datetime 对象）。
"""
import sqlite3

import pytest
from sqlalchemy import text

from src.common.constant import path_constant
from src.dao.database import _get_session_factory


@pytest.fixture(autouse=True)
def _protect_yande_data():
    """每个测试自动保存/恢复 yande_data 表（防 DELETE 测试污染生产数据）

    性能开销：每次测试 snapshot + restore 整张 yande_data 表（约 2904 行）。
    当前测试套件规模下约 +50ms/测试，100 个测试约 +5s，可接受。
    """
    Session = _get_session_factory()
    saved = _snapshot_yande_data(Session)
    yield
    _restore_yande_data(saved)


def _snapshot_yande_data(Session):
    """快照当前 yande_data 表的列结构 + 所有行（保留原始字符串类型）"""
    with Session() as s:
        cols = [row[1] for row in s.execute(
            text("PRAGMA table_info(yande_data)")
        ).fetchall()]
        rows = s.execute(text("SELECT * FROM yande_data")).fetchall()
    return {"cols": cols, "rows": [tuple(r) for r in rows]}


def _restore_yande_data(saved):
    """从快照恢复 yande_data 表内容（sqlite3 原生 DELETE + 批量 INSERT）"""
    if not saved["cols"]:
        return
    conn = sqlite3.connect(path_constant.sqlite_file)
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM yande_data")
        col_list = ",".join(saved["cols"])
        placeholders = ",".join(["?"] * len(saved["cols"]))
        sql = f"INSERT INTO yande_data ({col_list}) VALUES ({placeholders})"
        BATCH = 500
        for i in range(0, len(saved["rows"]), BATCH):
            cur.executemany(sql, saved["rows"][i:i + BATCH])
        conn.commit()
    finally:
        conn.close()